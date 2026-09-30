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
            "status": "active",
        },
        tags=["null", "crash", "parser"],
    )
    pre = _preflight(
        capsys, task="fix the null pointer crash in the parser", cwd=str(repo_dir)
    )
    assert "M1" in pre["memory"]["injection"]["memory_ids"], "recall must feed the loop"

    # `skill_used` is the host's own statement of what it applied. Without it a
    # successful run credits nothing — recall alone is not evidence (R-006).
    code, doc = _postflight(
        capsys,
        pre,
        cwd=str(repo_dir),
        outcome="success",
        quality_score=4.5,
        skill_used="parser",
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


# ── P4: the gate has to be usable by a person at a terminal ────────────
def _settle_payload(capsys, task="fix the null pointer crash in the parser", **extra):
    pre = _preflight(capsys, task=task, **extra)
    return _postflight(capsys, pre, cwd=extra.get("cwd", ""))


def test_doctor_json_is_machine_readable_and_names_the_versions(capsys, store):
    """The plugin probes this before it speaks; a paragraph is not a handshake."""
    store.upsert_memory({"memory_id": "M1", "type": "semantic", "title": "a", "body": "b"})

    code = main(["doctor", "--json"])
    document = json.loads(capsys.readouterr().out)

    assert code == 0
    assert document["ok"] is True
    assert document["contract_version"]
    assert set(document["supported_versions"]) >= {"1.1", "1.2"}
    assert document["schema"]["installed"] == document["schema"]["expected"]
    assert document["paths"]["database"].endswith("aos.db")
    assert document["features"]["learning_gate"] is True
    # A handshake document carries versions and counts, never the store's contents.
    assert "memory bodies" not in json.dumps(document, ensure_ascii=False)


def test_doctor_json_reports_the_store_as_it_really_is(capsys, store):
    from aos.core.memory.authoring import new_memory

    store.upsert_memory(new_memory(title="a", body="b", verified=True, status="active"))
    store.upsert_memory(new_memory(title="c", body="d"))

    main(["doctor", "--json"])
    document = json.loads(capsys.readouterr().out)

    assert document["memories"]["total"] == 2
    assert document["memories"]["recallable"] == 1, "only the approved row may be recalled"
    assert document["memories"]["without_dedupe_key"] == 0, "every writer fills the key now"


def test_memory_refresh_backfills_keys_and_is_idempotent(capsys, store):
    from aos.core.memory.authoring import new_memory

    store.upsert_memory(new_memory(title="a", body="b", verified=True, status="active"))
    store._conn.execute("UPDATE memories SET dedupe_key = ''")
    store._conn.commit()

    code = main(["memory", "refresh", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(report["dedupe_keys_filled"]) == 1

    main(["memory", "refresh", "--json"])
    again = json.loads(capsys.readouterr().out)

    assert again["dedupe_keys_filled"] == [], "a second pass changes nothing"
    assert again["expired"] == []


def test_memory_refresh_expires_by_ladder_not_by_deletion(capsys, store):
    from aos.core.memory.authoring import new_memory

    store.upsert_memory(
        new_memory(title="JDK 17 is the runtime", body="build with LTS", verified=True, status="verified")
    )
    memory_id = store.list_memories()[0]["memory_id"]
    store._conn.execute(
        "UPDATE memories SET revalidate_after = '2026-01-01' WHERE memory_id = ?", (memory_id,)
    )
    store._conn.commit()

    main(["memory", "refresh", "--json", "--today", "2026-09-30"])
    first = json.loads(capsys.readouterr().out)
    assert first["expired"] == [
        {"memory_id": memory_id, "from": "verified", "to": "active", "revalidate_after": "2026-01-01"}
    ]
    assert store.get_memory(memory_id)["status"] == "active"

    main(["memory", "refresh", "--json", "--today", "2026-09-30"])
    second = json.loads(capsys.readouterr().out)
    assert second["expired"][0]["to"] == "deprecated"
    assert store.get_memory(memory_id) is not None, "expiry retires, it does not delete"


def test_labelling_a_run_shows_its_consequence_in_the_same_command(capsys, store):
    """The defect this closed: a label wrote candidates the queue could not see."""
    pre = _preflight(capsys, task="修复 cache key 碰撞导致命中率下降的 bug", cwd="/home/dev/repos/warehouse")
    _postflight(capsys, pre, cwd="/home/dev/repos/warehouse")

    _, listed = _call(capsys, ["review", "list", "--json"], {})
    label_id = [r for r in listed if r["kind"] == "outcome_label"][0]["review_id"]

    code, result = _call(capsys, ["review", "label", str(label_id), "--outcome", "failure"], {})

    assert code == 0
    assert result["status"] == "approved", "the review's own state, not a verb for the call"
    assert result["learning"]["reviews_created"] == 1
    _, after = _call(capsys, ["review", "list", "--json"], {})
    assert any(r["kind"] == "promotion" and r["status"] == "pending" for r in after)


def test_review_list_does_not_offer_an_answered_question(capsys, store):
    pre = _preflight(capsys, task="修复 cache key 碰撞导致命中率下降的 bug", cwd="/home/dev/repos/warehouse")
    _postflight(capsys, pre, cwd="/home/dev/repos/warehouse")
    _, listed = _call(capsys, ["review", "list", "--json"], {})
    label_id = [r for r in listed if r["kind"] == "outcome_label"][0]["review_id"]
    capsys.readouterr()

    main(["review", "label", str(label_id), "--outcome", "failure"])
    capsys.readouterr()
    main(["review", "list"])
    shown = capsys.readouterr().out

    assert f"-> aos review label {label_id}" not in shown
    assert "已标注: failure" in shown


def test_batch_labelling_answers_the_queue_in_one_line(capsys, store):
    ids = []
    for index in range(3):
        pre = _preflight(capsys, task=f"任务 {index} 失败了", cwd="/home/dev/repos/warehouse", task_id=f"B{index}")
        _postflight(capsys, pre, cwd="/home/dev/repos/warehouse")
    _, listed = _call(capsys, ["review", "list", "--json"], {})
    ids = [r["review_id"] for r in listed if r["kind"] == "outcome_label"]
    assert len(ids) == 3

    code, result = _call(capsys, ["review", "label", *[str(i) for i in ids], "--outcome", "failure"], {})

    assert code == 0
    assert sorted(result["labelled"]) == sorted(ids)
    assert result["skipped"] == []


def test_batch_labelling_reports_what_it_refused(capsys, store):
    pre = _preflight(capsys, task="只有一个待标注", cwd="/home/dev/repos/warehouse")
    _postflight(capsys, pre, cwd="/home/dev/repos/warehouse")
    _, listed = _call(capsys, ["review", "list", "--json"], {})
    only = [r for r in listed if r["kind"] == "outcome_label"][0]["review_id"]
    capsys.readouterr()
    main(["review", "label", str(only), "--outcome", "failure"])
    capsys.readouterr()  # drain the first answer before reading the second call

    code, result = _call(capsys, ["review", "label", str(only), "9999", "--outcome", "failure"], {})

    assert code == 1
    assert result["labelled"] == []
    assert {s["status"] for s in result["skipped"]} == {"already_decided", "not_found"}


def test_review_sync_settles_candidates_without_another_run(capsys, store):
    from aos.core.memory import evolve
    from aos.core.memory.record import proposal_for_loop, record_outcome

    record_outcome(
        loop_id="L9",
        outcome="failure",
        quality_score=0.0,
        memories_used=[],
        needs_review=False,
        source_hash="h9",
        proposal=proposal_for_loop(
            loop_id="L9", task_text="一个值得记住的失败", outcome="failure", cwd="/home/dev/repos/warehouse"
        ),
        store=store,
    )

    code, summary = _call(capsys, ["review", "sync"], {})

    assert code == 0
    assert summary["summary"]["reviews_created"] == 1


def test_degraded_preflight_says_why(capsys):
    """A document that degrades in silence sends the human to the database."""
    code, doc = _call(
        capsys,
        ["preflight", "--payload-stdin"],
        {"schema_version": "1.2", "task": "随便一件完全没有线索的事", "cwd": "/tmp/nowhere"},
    )

    assert code == 0
    if doc["aos_status"] == "degraded":
        assert doc["warnings"], "degraded without an explanation is not a diagnosis"
