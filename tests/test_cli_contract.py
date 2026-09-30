"""The CLI is where a host's request becomes engine state.

Nothing else in the suite crosses the stdin/stdout boundary, and that is
exactly how ``outcome`` went unread for as long as it did: the lifecycle
accepted the parameter, the contract had no field for it, and no test ever
piped a payload in to find out.
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from aos.cli.main import BAD_REQUEST, main
from aos.core.memory.store import MemoryStore

# ── helpers ────────────────────────────────────────────────────────────
def _call(capsys, argv, payload):
    """Drive one CLI invocation over stdin and return (exit_code, document)."""
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        code = main(argv)
    finally:
        sys.stdin = sys.__stdin__
    out = capsys.readouterr().out.strip()
    return code, (json.loads(out) if out else None)


def _preflight(capsys, task="fix the null pointer crash in the parser", **extra):
    code, doc = _call(
        capsys, ["preflight", "--payload-stdin"], {"phase": "preflight", "task": task, **extra}
    )
    assert code == 0, doc
    return doc


def _postflight(capsys, pre, **payload_extra):
    return _call(
        capsys,
        ["postflight", "--payload-stdin"],
        {
            "phase": "postflight",
            "task_id": pre["task_id"],
            "loop_id": pre["loop_id"],
            **payload_extra,
        },
    )


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


@pytest.fixture
def repo_dir(tmp_path):
    """A git project, so evidence collection has something real to read."""
    import subprocess
    from pathlib import Path

    path = Path(tmp_path / "proj")
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=T",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=path,
        check=True,
    )
    return path


# ── the outcome channel (breakpoint 3) ─────────────────────────────────
def test_postflight_forwards_a_reported_failure(store, repo_dir, capsys):
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(capsys, pre, outcome="failure", cwd=str(repo_dir))

    assert code == 0
    assert doc["final_status"] == "failed"
    row = store.list_observations()[-1]
    assert row["outcome"] == "failure"
    # Before this, every delegated run wrote "success" here regardless of fact.
    assert row["outcome"] != "success"


def test_postflight_without_an_outcome_is_not_recorded_as_success(repo_dir, capsys, store):
    """An unlabeled delegated run is partial, and says so.

    The engine does not know how the task went; reporting success was the
    default that made the learning loop feed itself a constant.
    """
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(capsys, pre, cwd=str(repo_dir))

    assert code == 0
    assert doc["final_status"] == "partial"
    assert store.list_observations()[-1]["outcome"] == "partial"


def test_postflight_forwards_quality_score_and_yields_a_reinforce_candidate(store, repo_dir, capsys):
    store.upsert_memory(
        {
            "memory_id": "M1",
            "type": "procedural",
            "category": "backend",
            "title": "null guard",
            "body": "check for null before dereferencing",
            "evidence_level": "runtime_validated",
        },
        tags=["null", "crash", "parser"],
    )
    pre = _preflight(
        capsys, task="fix the null pointer crash in the parser", cwd=str(repo_dir)
    )
    assert "M1" in pre["memory"]["injection"]["memory_ids"], "recall must feed the loop"

    code, doc = _postflight(
        capsys, pre, cwd=str(repo_dir), outcome="success", quality_score=4.5
    )

    assert code == 0
    assert doc["learning"]["candidates_recorded"] >= 1
    types = {c["candidate_type"] for c in store.list_candidates()}
    assert "reinforce" in types


def test_postflight_forwards_a_failing_test_exit_code(repo_dir, capsys, store):
    """A nonzero exit code forces failure even with no reported outcome."""
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(capsys, pre, cwd=str(repo_dir), test_exit_code=1)

    assert code == 0
    assert store.list_observations()[-1]["outcome"] == "failure"
    assert doc["recovery"]["failures_detected"] >= 0  # loop closed, not swallowed


def test_postflight_forwards_expected_files_and_no_validate(repo_dir, capsys):
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(
        capsys,
        pre,
        cwd=str(repo_dir),
        expected_files=["src/app.py"],
        validate=False,
        test_command="",
        test_stdout="",
        test_stderr="",
        compile_command="",
    )
    assert code == 0
    assert doc["evidence"]["path"]


# ── the request boundary is visible, not silent ────────────────────────
def test_host_signals_are_weighed_instead_of_ignored(repo_dir, store, capsys):
    """A nested ``signals`` object must reach the verdict.

    This replaces the guard that used to demand a warning for ``signals`` — the
    field is read now. It is the plugin's whole channel: opencode cannot say
    "this failed", but it can say the test exited 1, and that is enough.
    """
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(
        capsys, pre, cwd=str(repo_dir), signals={"test_exit_code": 1, "tool_errors": 3}
    )

    assert code == 0
    assert doc["final_status"] == "failed"
    assert doc["learning"]["needs_review"] is True
    assert not any("signals" in warning for warning in doc["warnings"])

    rows = [o for o in store.list_observations(loop_id=pre["loop_id"]) if o["memory_id"] is None]
    assert len(rows) == 1
    observation = rows[0]
    assert observation["outcome"] == "failure"
    assert observation["synthesised"] is True
    assert observation["needs_review"] is True
    assert observation["signals"]["test_exit_code"] == 1
    # Nothing was reinforced or weakened on a verdict the engine had to guess at.
    assert observation["confidence"] < 0.60


def test_genuinely_unknown_fields_still_warn(repo_dir, capsys):
    """``signals`` became readable; the warning channel did not go away with it."""
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(
        capsys, pre, cwd=str(repo_dir), tool_errors=2, definitely_not_a_field=True
    )
    assert code == 0
    warnings = " ".join(doc["warnings"])
    assert "definitely_not_a_field" in warnings
    assert "tool_errors" not in warnings


def test_unknown_preflight_fields_are_reported_too(capsys):
    code, doc = _call(
        capsys,
        ["preflight", "--payload-stdin"],
        {"phase": "preflight", "task": "fix the crash", "memoryMode": "enabled"},
    )
    assert code == 0
    assert any("memoryMode" in warning for warning in doc["warnings"])


def test_missing_required_field_returns_fallback_and_nonzero_exit(capsys):
    code, doc = _call(capsys, ["postflight", "--payload-stdin"], {"phase": "postflight"})

    assert code == BAD_REQUEST
    assert doc["aos_status"] == "fallback"
    assert doc["final_status"] == "failed"
    assert any("task_id" in warning for warning in doc["warnings"])


def test_empty_task_is_rejected(capsys):
    code, doc = _call(capsys, ["preflight", "--payload-stdin"], {"phase": "preflight", "task": "  "})
    assert code == BAD_REQUEST
    assert doc["aos_status"] == "fallback"


def test_mistyped_field_is_rejected_not_coerced(capsys, repo_dir):
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(capsys, pre, cwd=str(repo_dir), quality_score="great")

    assert code == BAD_REQUEST
    assert any("quality_score" in warning for warning in doc["warnings"])


def test_a_boolean_is_not_accepted_as_a_number(capsys, repo_dir):
    pre = _preflight(capsys, cwd=str(repo_dir))
    code, doc = _postflight(capsys, pre, cwd=str(repo_dir), test_exit_code=True)
    assert code == BAD_REQUEST


def test_unknown_schema_version_is_rejected_at_the_boundary(capsys):
    """The builder is lenient, the boundary is not.

    ``build_preflight`` answers an unknown declaration in its own version so a
    degrade is still parseable, but a request declaring a version we do not
    speak is refused outright: silently replying 1.1 to a host that believes it
    negotiated 1.2 is a worse trap than an honest rejection.
    """
    code, doc = _call(
        capsys,
        ["preflight", "--payload-stdin"],
        {"phase": "preflight", "task": "fix the crash", "schema_version": "2.0"},
    )
    assert code == BAD_REQUEST
    assert any("schema_version" in warning for warning in doc["warnings"])


def test_a_declared_1_0_request_is_still_served_1_0(capsys):
    code, doc = _call(
        capsys,
        ["preflight", "--payload-stdin"],
        {"phase": "preflight", "schema_version": "1.0", "task": "fix the crash"},
    )
    assert code == 0
    assert doc["schema_version"] == "1.0"


# ── doctor reports the schema without rewriting it ─────────────────────
def _db_version(db_path):
    import sqlite3

    from aos.core.memory import migrations

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return migrations.current_version(conn)
    finally:
        conn.close()


def test_doctor_names_the_schema_version(capsys):
    """The plugin will negotiate against `aos doctor`, so the version must be in it."""
    from aos.config import get_paths

    MemoryStore().close()  # build the database the ordinary way
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "schema:" in out
    assert f"v{_db_version(get_paths().db_path)} [OK]" in out


def test_doctor_does_not_migrate_a_behind_database(capsys, tmp_path):
    """Diagnosis must not be a write.

    `doctor` is what gets run when something already looks wrong; a diagnostic
    that rewrites the store on the way past turns an inspection into the
    incident it was asked about.
    """
    from aos.config import get_paths
    from aos.core.memory import migrations

    db = get_paths().db_path
    store = MemoryStore(db_path=db)
    store.close()
    conn = _v1_downgrade(db)

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "BEHIND" in out
    assert _db_version(db) == migrations.BASELINE_VERSION, "doctor must not have migrated"
    assert list(tmp_path.glob("*.bak")) == [], "doctor must not have backed anything up either"


def _v1_downgrade(db):
    """Stamp a migrated file back to v1 so there is something pending to report."""
    import sqlite3

    from aos.core.memory import migrations

    conn = sqlite3.connect(str(db))
    conn.execute(f"PRAGMA user_version = {migrations.BASELINE_VERSION}")
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
                 (str(migrations.BASELINE_VERSION),))
    conn.commit()
    return conn
