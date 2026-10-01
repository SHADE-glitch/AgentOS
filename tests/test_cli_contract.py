"""The CLI is where a host's request becomes engine state.

Nothing else in the suite crosses the stdin/stdout boundary, and that is
exactly how ``outcome`` went unread for as long as it did: the lifecycle
accepted the parameter, the contract had no field for it, and no test ever
piped a payload in to find out.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aos.cli.main import BAD_REQUEST, main
from aos.core.memory.store import MemoryStore

REPO_ROOT = Path(__file__).resolve().parents[1]

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


def test_doctor_reports_whether_recall_found_anything(capsys, store):
    """The one number that says whether this layer is silent, not just empty.

    `observations` counts runs; it does not say whether a run got any memory back.
    A store that never matches the task language looks exactly like a healthy one
    from that count — which is how the Chinese-recall defect (V) could sit there for
    as long as it did. Read out over the loop's own runs only: backfilled history is
    not evidence about recall, because nobody recalled anything for it.
    """
    store.add_observation(loop_id="LOOP-HIT", outcome="partial", session_id="ses-hit")
    store.log_retrieval(memory_id="M-SEED-X", score=0.4, rank=1, loop_id="LOOP-HIT", query_hash="Q1")
    store.add_observation(loop_id="LOOP-MISS", outcome="partial", session_id="ses-miss")
    store.add_observation(loop_id="BACKFILL-ses-x", outcome="partial", session_id="ses-x",
                          source="backfill")

    code = main(["doctor", "--json"])
    document = json.loads(capsys.readouterr().out)

    assert code == 0
    assert document["recall"] == {"runs": 2, "recalled": 1, "zero_recall": 1}, document.get("recall")


def test_memory_retire_is_a_supported_exit_from_recall_that_keeps_the_row(capsys, store, tmp_path):
    """The CLI has to offer the exit the gate implies: stop trusting a memory, keep its history.

    `aos memory` could add, seed, refresh and inspect, while the only writer of `status` was the
    promotion ladder — so a memory a human could see was junk stayed in every injection until it had
    been demoted five times (defect Z's bill), or until somebody ran an UPDATE against the database
    by hand, which is how a column quietly acquires a third writer.
    """
    cwd = str(tmp_path / "proj")
    Path(cwd).mkdir(parents=True, exist_ok=True)

    code = main([
        "memory", "add", "--verified", "--evidence-level", "runtime_validated",
        "--title", "kafka 消费失败先看重试次数", "--body", "先确认 retry 次数是否已经耗尽，再谈别的。",
        "--tags", "kafka,retry", "--category", "bugfix",
    ])
    assert code == 0
    memory_id = json.loads(capsys.readouterr().out)["memory_id"]
    task = "kafka 消费失败该先看什么"

    pre = _preflight(capsys, task=task, cwd=cwd)
    assert memory_id in pre["memory"]["injection"]["memory_ids"], "recalled while it is active"

    assert main(["memory", "retire", memory_id, "--reason", "写错了，从未成立"]) == 0
    capsys.readouterr()

    after = _preflight(capsys, task=task, cwd=cwd)
    assert memory_id not in (after["memory"]["injection"]["memory_ids"] or []), "retired must not be injected"

    assert main(["memory", "list"]) == 0
    listing = capsys.readouterr().out
    assert memory_id in listing and "deprecated" in listing, "retirement is not deletion"

    # A refusal costs nothing: no row, no write.
    assert main(["memory", "retire", "M-NOPE", "--reason", "不存在也要留痕吗"]) == 1


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


def test_review_approve_lets_the_human_write_the_lesson(capsys, store):
    """`--body` at the gate is the only place a `因为` can come from, so the wiring must be real.

    Flag plumbing is where this kind of feature quietly dies: `--when` has to land in
    `when_to_apply`, the row has to carry the person's words instead of the incident echo, and an
    approval that was already decided must still exit non-zero rather than pretend.
    """
    from aos.core.memory import evolve
    from aos.core.memory.record import proposal_for_loop, record_outcome

    proposal = proposal_for_loop(
        loop_id="L11", task_text="缓存键碰撞导致命中率下降", outcome="failure",
        cwd="/home/dev/repos/warehouse", category="bugfix", skills=["bugfix"],
    )
    record_outcome(
        loop_id="L11", outcome="failure", quality_score=0.0, memories_used=[],
        needs_review=False, source_hash="h11", proposal=proposal, store=store,
    )
    evolve.run_learning(store=store)
    review_id = [r["review_id"] for r in store.list_reviews(status="pending")][0]

    code = main([
        "review", "approve", str(review_id),
        "--body", "不要按配置名取缓存键，因为它会被两个项目各自解析一遍；用解析后的真实路径。",
        "--when", "新增缓存层或改配置解析顺序时",
    ])
    assert code == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["promotion"]["status"] == "created", emitted

    memory = store.get_memory(proposal["memory_id"])
    assert memory["body"].startswith("不要按配置名取缓存键"), memory["body"]
    assert "未归因" not in memory["body"], "the human filled the hole, so the draft must not keep claiming it"
    assert memory["when_to_apply"] == "新增缓存层或改配置解析顺序时", "--when must reach when_to_apply"

    assert main(["review", "approve", str(review_id), "--body", "再来一次"]) == 1


def test_review_approve_takes_the_subject_the_human_names(capsys, store):
    """`--tags` at the gate has to reach the side table the ranker reads, or AH's fix is a disappearance.

    The ranking half of AH stops the router's `fallback` bucket from counting as a subject; that
    leaves an approved lesson with nothing to be found by. This flag is the replacement, so the
    plumbing is the feature: comma-split words must land in `memory_tags`, and an empty value must
    be refused before the row exists rather than silently approving it subject-less.
    """
    from aos.core.memory import evolve
    from aos.core.memory.record import proposal_for_loop, record_outcome

    proposal = proposal_for_loop(
        loop_id="L12", task_text="配置目录解析成了两个不同的路径", outcome="failure",
        cwd="/home/dev/repos/tracker", category="bugfix", skills=["bugfix"],
    )
    record_outcome(
        loop_id="L12", outcome="failure", quality_score=0.0, memories_used=[],
        needs_review=False, source_hash="h12", proposal=proposal, store=store,
    )
    evolve.run_learning(store=store)
    review_id = [r["review_id"] for r in store.list_reviews(status="pending")][0]

    # The lever has to be visible at the moment the person is reading the queue, not only in a
    # help screen they would have to already know to open.
    main(["review", "list"])
    assert "--tags" in capsys.readouterr().out, "the queue must name the subject flag it now needs"

    assert main(["review", "approve", str(review_id), "--tags", " , "]) == 1
    refused = capsys.readouterr()
    assert "tags" in refused.err, refused.err
    assert store.get_memory(proposal["memory_id"]) is None, "an empty subject must not create the row"

    code = main(["review", "approve", str(review_id), "--tags", "配置文件, 目录, glob"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["promotion"]["status"] == "created"

    memory = next(m for m in store.memories_for_scoring() if m["memory_id"] == proposal["memory_id"])
    assert sorted(memory["tags"]) == sorted(["配置文件", "目录", "glob"]), memory["tags"]
    assert "bugfix" not in memory["tags"], "the subject the human wrote replaces the router's guess"


def test_a_tool_trace_reaches_the_reviewer_who_decides(capsys, store):
    """A run's account is only worth collecting if the person judging the run can read it.

    The label review already carries every reported signal in its evidence, so the failure mode here
    is not missing data but unreadable data: printing `tool_trace=[{'n': 1, ...}]` into the 信号 line
    would bury both the account and the rest of the signals in a Python repr. So the trajectory gets
    its own line, and the raw list is kept out of the summary.
    """
    pre = _preflight(capsys, task="CI 构建超时，glob 把依赖目录也吞进去了", cwd="/home/dev/repos/warehouse")
    _postflight(
        capsys, pre, cwd="/home/dev/repos/warehouse",
        tool_trace=[
            {"n": 1, "tool": "bash", "method": "npm test", "exit": 1, "ok": False},
            {"n": 2, "tool": "bash", "method": "python -m pytest", "exit": 0, "ok": True},
        ],
        tool_calls=2,
    )
    capsys.readouterr()
    main(["review", "list"])
    shown = capsys.readouterr().out

    assert "过程：#1 npm test 失败 → #2 python -m pytest 通过" in shown, shown
    assert "[{'n'" not in shown, "a Python repr is not how a human reads a trajectory"
    assert "tool_trace=" not in shown, "and the raw key must not double-print it"


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


# ── P6: the plugin's half of the seam ──────────────────────────────────
def test_the_plugin_test_suite_runs_and_passes():
    """`node --test` over tests/js is part of the suite, not an optional extra.

    Deliberately not skipped when node is missing: the non-interference properties
    it checks are the condition the plugin is allowed to exist under, and a guard
    that skips is a guard that passed.
    """
    node = shutil.which("node")
    assert node, "node is required to run the plugin's tests (see integrations/opencode/README.md)"

    finished = subprocess.run(
        [node, "--test", "tests/js/plugin.test.mjs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert finished.returncode == 0, finished.stdout[-4000:] + finished.stderr[-2000:]
    assert "# fail 0" in finished.stdout


def _js_without_comments(source: str) -> str:
    """Strip `//` and block comments; keep the code and the strings intact."""
    out, i, n = [], 0, len(source)
    while i < n:
        two = source[i : i + 2]
        if two == "//":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if two == "/*":
            end = source.index("*/", i + 2)
            i = end + 2
            out.append(" ")
            continue
        out.append(source[i])
        i += 1
    return "".join(out)


def _js_payload_keys(source: str, marker: str) -> set[str]:
    """The top-level keys of the object literal passed to `ask(cfg, "<phase>", {…})`.

    A scanner rather than a regex over the whole file: a key only counts when it sits
    at the payload object's own depth, so a nested literal, a call argument or a
    string that happens to contain a colon cannot be mistaken for one.
    """
    src = _js_without_comments(source)
    open_at = src.index("{", src.index(marker))
    depth = 0
    keys: set[str] = set()
    i = open_at
    while i < len(src):
        char = src[i]
        if char in "\"'`":
            quote = char
            i += 1
            while i < len(src):
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    break
                i += 1
            i += 1
            continue
        if char in "{[(":
            depth += 1
            i += 1
            continue
        if char in "})]":
            depth -= 1
            if depth == 0:
                break
            i += 1
            continue
        if char == ":" and depth == 1:
            j = i - 1
            while j >= 0 and (src[j].isalnum() or src[j] in "_$"):
                j -= 1
            name = src[j + 1 : i]
            if name and (name[0].isalpha() or name[0] == "_"):
                keys.add(name)
        i += 1
    return keys


def test_the_plugin_own_payload_fields_are_the_ones_the_contract_reads():
    """The seam's other half is written in JS, so read it — do not retype it.

    The field lists in the rest of this file are hand-copied literals: add a key to
    the plugin and nothing fails until a host ships it and the engine reports it as
    ignored at runtime. That is how `outcome` went unread for as long as it did —
    designed on one side and typed on the other. Parsing the source closes the gap,
    and gives `PLUGIN_POSTFLIGHT_REQUEST_FIELDS` its first reader outside its own
    module, so it cannot become a list that describes nothing.
    """
    from aos.contract import PLUGIN_POSTFLIGHT_REQUEST_FIELDS
    from aos.contract.schema import REQUEST_FIELDS, SIGNAL_FIELDS

    source = (REPO_ROOT / "integrations" / "opencode" / "plugin" / "agent-os.js").read_text(
        encoding="utf-8"
    )

    pre = _js_payload_keys(source, 'ask(cfg, "preflight"')
    post = _js_payload_keys(source, 'ask(cfg, "postflight"')
    signals = set(re.findall(r"signals\.([a-z_]+)\s*=", _js_without_comments(source)))

    assert pre and post, "the payload literals were not found — the plugin's shape changed"
    assert pre <= REQUEST_FIELDS["preflight"], sorted(pre - REQUEST_FIELDS["preflight"])
    assert post <= REQUEST_FIELDS["postflight"], sorted(post - REQUEST_FIELDS["postflight"])
    assert signals, "the plugin sends a signals object; if it stopped, say so here"
    assert signals <= SIGNAL_FIELDS, sorted(signals - SIGNAL_FIELDS)
    # Everything the plugin can put in `signals` is a field the gate claims to accept.
    assert signals <= PLUGIN_POSTFLIGHT_REQUEST_FIELDS
    assert {"tool_errors", "session_error", "user_interrupted", "response_summary",
            "tool_trace", "tool_calls"} == signals, (
        "the signal set the host can observe changed; the synthesis and this guard "
        "have to be updated together, not one time out of two"
    )
    # And the two that are new since the trajectory landed must stay exactly as uninfluential as
    # `response_summary`: what a run *did* is material for the person at the gate, not a claim
    # about how well it went. Weighting the attempt count would give a thrashing run a different
    # confidence from a clean one, which is the opposite of what coverage measures.
    from aos.core.memory.policy import load_policy

    weights = load_policy("outcome")["weights"]
    assert weights["response_summary"] == 0.00, (
        "response_summary is material for a reviewer, never evidence in a verdict"
    )
    assert weights["tool_trace"] == 0.00 and weights["tool_calls"] == 0.00, (
        "a trajectory describes the run; it does not judge it"
    )


def test_the_models_answer_reaches_the_proposal_that_a_human_reads(capsys, store):
    """The whole seam for defect AG's material: host signal → observation → draft, without a verdict.

    A JS test can prove the plugin sends it and a Python test can prove the draft quotes it; only
    this one proves the two ends are the same field, and that quoting the answer leaves the
    synthesized verdict and confidence exactly where they were.
    """
    pre = _preflight(capsys, task="为什么按配置名取缓存键会让命中率掉下来", cwd="/home/dev/repos/warehouse")
    capsys.readouterr()
    code, doc = _postflight(
        capsys, pre,
        signals={"response_summary": "因为两个项目会各自解析同一份配置，键空间就分叉了。"},
    )

    assert code == 0, doc
    row = store.list_observations(loop_id=pre["loop_id"])[0]
    assert "分叉" in (row["signals"] or {}).get("response_summary", ""), row["signals"]
    assert row["needs_review"] is True, "an answer alone is not evidence that the run went well"
    assert row["confidence"] == 0.0, "the prose carries no mass: weight 0.00, end to end"

    from aos.core.memory.record import proposal_for_loop

    draft = proposal_for_loop(
        loop_id=pre["loop_id"], task_text="为什么按配置名取缓存键会让命中率掉下来", outcome="failure",
        cwd="/home/dev/repos/warehouse", category="bugfix", skills=["bugfix"],
        signals=dict(row["signals"], **{"task": "为什么按配置名取缓存键会让命中率掉下来"}),
    )
    assert "模型自述（未核实）" in draft["body"], draft["body"]
    assert "未归因" in draft["body"], "quoting the answer must not close the cause-hole it cannot fill"


def test_every_field_the_plugin_sends_is_one_the_engine_reads(capsys):
    """The two halves of the seam are written in different languages; this is the shared check.

    A key the engine does not read comes back named in `warnings` rather than
    being dropped in silence, so this fails the moment the plugin starts sending
    something the contract never agreed to read — the drift that left the outcome
    channel missing in the first place.
    """
    pre = _preflight(capsys, task="修复 cache key 碰撞", cwd="/fixture/project", session_id="ses-1")
    capsys.readouterr()

    code, doc = _postflight(
        capsys,
        pre,
        cwd="/fixture/project",
        provider="host_delegate",
        signals={"tool_errors": 1, "session_error": "模型超时"},
    )

    assert code == 0
    assert doc["warnings"] == [], doc["warnings"]
    # The session error is decisive for the *status*…
    assert doc["final_status"] == "failed"
    # …while two signals out of the contract's set is not enough coverage to name
    # an outcome for learning. Low mass still asks a person: that is the designed
    # main path, not a loss of the signal.
    assert doc["learning"]["needs_review"] is True


def test_plugin_payload_with_an_unknown_key_is_named_not_swallowed(capsys):
    pre = _preflight(capsys, task="修复 cache key 碰撞", cwd="/fixture/project", session_id="ses-2")
    capsys.readouterr()

    code, doc = _call(
        capsys,
        ["postflight", "--payload-stdin"],
        {
            "schema_version": "1.2",
            "phase": "postflight",
            "task_id": pre["task_id"],
            "loop_id": pre["loop_id"],
            "session_id": pre["session_id"],
            "totally_new_field": True,
        },
    )

    assert code == 0
    assert any("totally_new_field" in warning for warning in doc["warnings"])


def test_the_unattributed_hint_does_not_point_at_a_dead_command(capsys):
    """A hint that names a command which can no longer run teaches the queue is broken.

    Labelling without `--skill` records the verdict and blames nothing, and the CLI
    says so — but the review is approved by that same call, so repeating it with
    `--skill` returns `already_decided`. The hint has to say what is lost and when the
    next chance is, not offer a command that cannot succeed.
    """
    from aos.core.loop import lifecycle

    pre = lifecycle.preflight(task="修复 cache key 碰撞", cwd="/tmp", session_id="ses-hint")
    lifecycle.postflight(task_id=pre["task_id"], loop_id=pre["loop_id"], session_id="ses-hint", cwd="/tmp")

    with MemoryStore() as store:
        pending = [r for r in store.list_reviews(status="pending") if r["kind"] == "outcome_label"]
    review_id = pending[0]["review_id"]

    sys.stdin = io.StringIO("")
    try:
        main(["review", "label", str(review_id), "--outcome", "failure"])
    finally:
        sys.stdin = sys.__stdin__
    err = capsys.readouterr().err

    assert "没有归因任何记忆" in err, "the loss has to be said out loud"
    assert f"label {review_id} --outcome" not in err, "and no command may be suggested that is now impossible"
