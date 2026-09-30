"""Read-only history backfill: the last mile to real data, and the privacy edge.

The source database is somebody else's, and it holds conversations. These tests
are as much about what must *not* happen — a wipe after a failed open, a title
copied into our store, one of the two sessions at the same millisecond skipped
forever — as about the counts landing.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from aos import backfill
from aos.core.loop import lifecycle
from aos.core.memory import evolve
from aos.core.memory.store import MemoryStore

SECRET_TITLE = "如何把客户的手机号导出"
SECRET_TEXT = "客户的手机号是 13800000000"


def _source(tmp_path, *, sessions=2, same_timestamp=False, with_todos=True, broken_json=False):
    """A fixture shaped like opencode's database: same tables, same JSON blob."""
    path = tmp_path / "opencode.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT,
            agent TEXT, model TEXT, time_updated INTEGER
        );
        CREATE TABLE part (
            id TEXT PRIMARY KEY, session_id TEXT, data TEXT, time_created INTEGER
        );
        CREATE TABLE todo (session_id TEXT, content TEXT, status TEXT);
        """
    )
    stamp = 1_790_000_000_000
    for index in range(sessions):
        when = stamp if same_timestamp else stamp + index
        conn.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?,?)",
            (
                f"ses_{index}",
                "proj",
                "/home/dev/repos/warehouse",
                SECRET_TITLE,
                "build",
                json.dumps({"id": "claude-x", "providerID": "opencode", "variant": "max"}),
                when,
            ),
        )
        parts = [
            {"type": "text", "text": SECRET_TEXT},
            {"type": "tool", "tool": "bash", "state": {"status": "error", "error": SECRET_TEXT}},
            {"type": "tool", "tool": "edit", "state": {"status": "completed", "output": SECRET_TEXT}},
            {"type": "patch", "hash": "abc"},
        ]
        for part_index, part in enumerate(parts):
            conn.execute(
                "INSERT INTO part VALUES (?,?,?,?)",
                (
                    f"par_{index}_{part_index}",
                    f"ses_{index}",
                    "{not json" if broken_json and part_index == 0 else json.dumps(part),
                    when + part_index,
                ),
            )
        if with_todos:
            conn.execute("INSERT INTO todo VALUES (?,?,?)", (f"ses_{index}", SECRET_TEXT, "pending"))
            conn.execute("INSERT INTO todo VALUES (?,?,?)", (f"ses_{index}", SECRET_TEXT, "completed"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def store():
    instance = MemoryStore()
    yield instance
    instance.close()


# ── off by default ─────────────────────────────────────────────────────
def test_nothing_is_read_when_the_source_is_not_configured(store, monkeypatch):
    monkeypatch.delenv(backfill.ENV_BACKFILL_DB, raising=False)

    assert backfill.plan() == {"enabled": False, "reason": f"{backfill.ENV_BACKFILL_DB} is not set; nothing is read"}
    report = backfill.run(store=store)

    assert report["ok"] is False
    assert store.list_observations() == []


def test_a_moved_or_missing_source_is_refused_before_any_write(store, monkeypatch, tmp_path):
    """The R-007 ordering rule: the check that the source exists comes first."""
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(tmp_path / "gone.db"))

    report = backfill.run(store=store, reset=True, apply=True)

    assert report["ok"] is False
    assert "not found" in report["reason"]


# ── what lands ─────────────────────────────────────────────────────────
def test_a_backfilled_session_lands_as_evidence_and_not_as_a_verdict(store, monkeypatch, tmp_path):
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path)))

    report = backfill.run(store=store, apply=True)

    assert report["ok"] and report["written"] == 2
    rows = store.list_observations()
    assert {row["source"] for row in rows} == {"backfill"}
    observation = rows[0]
    assert observation["outcome"] == "partial", "history cannot be re-judged into success"
    assert observation["confidence"] == 0.0
    assert observation["signals"]["tool_errors"] == 1
    assert observation["signals"]["todos_unfinished"] == 1
    assert observation["signals"]["diff"] == 1


def test_the_second_pass_reads_only_new_ground(store, monkeypatch, tmp_path):
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path)))
    backfill.run(store=store, apply=True)
    mark_before = store.backfill_watermark(backfill.WATERMARK_KEY)

    again = backfill.run(store=store, apply=True)

    assert again["sessions_seen"] == 0
    assert again["watermark"] == {"time": mark_before["watermark_time"], "id": mark_before["watermark_id"]}
    assert len(store.list_observations()) == 2


def test_sessions_sharing_a_timestamp_are_not_skipped(store, monkeypatch, tmp_path):
    """The specific bug the composite watermark exists for.

    `WHERE time > mark` would ingest one of these two and then never look at the
    other again, because they carry the same instant.
    """
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path, sessions=2, same_timestamp=True)))

    report = backfill.run(store=store, apply=True)

    assert report["written"] == 2, "both rows at the winning timestamp must be read"
    assert {row["session_id"] for row in store.list_observations()} == {"ses_0", "ses_1"}


def test_a_grown_session_is_updated_rather_than_appended(store, monkeypatch, tmp_path):
    path = _source(tmp_path, sessions=1)
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(path))
    backfill.run(store=store, apply=True)

    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO part VALUES ('par_9','ses_0',?,?)" , (json.dumps({"type": "patch"}), 1))
    conn.execute("UPDATE session SET time_updated = time_updated + 1 WHERE id='ses_0'")
    conn.commit()
    conn.close()
    report = backfill.run(store=store, apply=True)

    rows = store.list_observations()
    assert len(rows) == 1, "one run is one observation, however often it is re-read"
    assert rows[0]["signals"]["diff"] == 2


# ── what must never happen ─────────────────────────────────────────────
def test_no_conversation_text_is_copied_into_our_store(store, monkeypatch, tmp_path):
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path)))

    backfill.run(store=store, apply=True)

    stored = json.dumps(
        [dict(row) for row in store.list_observations()], default=str
    ) + json.dumps([dict(row) for row in store.list_memories()], default=str)
    assert SECRET_TEXT not in stored
    assert SECRET_TITLE not in stored
    schema = store._conn.execute("SELECT sql FROM sqlite_master").fetchall()
    assert not any(SECRET_TEXT in str(row[0] or "") for row in schema)
    # The project name is the only thing from `directory` that travels, and it is
    # a scope label rather than a path.
    assert store.list_observations()[0]["signals"]["project"] == "warehouse"
    assert "/home/dev" not in stored
    # `model` is a JSON object in the source; only its id may travel, not the
    # other tool's configuration around it.
    model = store.list_observations()[0]["signals"]["model"]
    assert model == "claude-x", model


def test_reset_clears_our_rows_only_after_the_source_opened(store, monkeypatch, tmp_path):
    path = _source(tmp_path)
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(path))
    backfill.run(store=store, apply=True)
    before = store.list_observations()
    assert len(before) == 2

    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(tmp_path / "moved-away.db"))
    report = backfill.run(store=store, reset=True, apply=True)

    assert report["ok"] is False
    assert len(store.list_observations()) == len(before), "a failed open must leave the rows alone"


def test_a_source_without_todos_degrades_instead_of_failing(store, monkeypatch, tmp_path):
    path = _source(tmp_path, with_todos=False)
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(path))

    report = backfill.run(store=store, apply=True)

    assert report["ok"]
    assert report["probe"]["available"]["todos"] is True  # table exists, rows absent
    assert store.list_observations()[0]["signals"]["todos_unfinished"] == 0


def test_malformed_part_json_is_counted_as_unknown_not_assumed_clean(store, monkeypatch, tmp_path):
    """A part we cannot parse is not evidence that nothing went wrong."""
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path, sessions=1, broken_json=True)))

    report = backfill.run(store=store, apply=True)

    assert report["ok"]
    signals = store.list_observations()[0]["signals"]
    assert signals.get("parts_unreadable") is True
    # The whole session's parts went unread, so "tool_errors" is absent rather
    # than 0: the gap is visible, and coverage drops instead of being faked.
    assert "tool_errors" not in signals
    assert signals["todos_unfinished"] == 1, "what could be read was still read"


# ── the boundary with the learning path ────────────────────────────────
def test_backfilled_history_never_enters_the_human_queue(store, monkeypatch, tmp_path):
    """A person cannot be asked to judge a run nobody observed."""
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path, sessions=3)))

    backfill.run(store=store, apply=True)
    report = evolve.run_learning(store=store)

    assert report["summary"]["outcome_labels_queued"] == 0
    assert evolve.list_reviews(store=store) == []
    assert store.list_candidates() == []


def test_backfilled_history_does_not_change_what_recall_offers(store, monkeypatch, tmp_path):
    """It is context about the past, not a memory with standing."""
    from aos.core.memory.retrieve import retrieve

    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path)))
    query = {
        "task_text": "cache key 碰撞",
        "category": "bugfix",
        "domains": ["bugfix"],
        "roles": [],
        "keywords": ["cache"],
        "scope_project": "warehouse",
    }
    before = retrieve(query, store=store, log=False)
    backfill.run(store=store, apply=True)
    after = retrieve(query, store=store, log=False)

    assert [row["memory_id"] for row in before["results"]] == [row["memory_id"] for row in after["results"]]


def test_doctor_keeps_read_history_out_of_the_observed_run_count(store, monkeypatch, tmp_path, capsys):
    """The criterion that decides whether this layer earns its keep counts runs, not rows.

    174 backfilled sessions and 174 real runs are the same number and mean
    opposite things, so `doctor` has to publish the split rather than a total.
    """
    from aos.cli.main import main

    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path, sessions=2)))
    backfill.run(store=store, apply=True)
    pre = lifecycle.preflight(task="一次会报告回来的运行", cwd=str(tmp_path), session_id="ses-hot")
    lifecycle.postflight(
        task_id=pre["task_id"],
        loop_id=pre["loop_id"],
        session_id="ses-hot",
        cwd=str(tmp_path),
        outcome="failure",
        quality_score=0.0,
    )

    main(["doctor", "--json"])
    document = json.loads(capsys.readouterr().out)

    assert document["observations"]["backfill"] == 2
    assert document["observations"]["hot"] >= 1
    assert "total" not in document["observations"], "a summed count invites the wrong reading"


def test_the_cli_reports_the_plan_without_writing(store, tmp_path, monkeypatch):
    monkeypatch.setenv(backfill.ENV_BACKFILL_DB, str(_source(tmp_path)))
    plan = backfill.plan()

    assert plan["enabled"] is True
    assert plan["sessions_total"] == 2
    assert plan["with_evidence"] == 2
    assert store.list_observations() == [], "plan() writes nothing"
