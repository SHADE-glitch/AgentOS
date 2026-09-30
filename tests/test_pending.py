"""The pending record is the plugin's only bridge from a session to a loop.

opencode's idle event says which conversation went quiet and nothing else, so
everything the plugin can report afterwards depends on this mapping existing — and
on a run that never reported back leaving a trace somebody can read.
"""

from __future__ import annotations

import json

import pytest

from aos.config import get_paths
from aos.core.loop import lifecycle, pending


def _pending_dir():
    return get_paths().pending_dir


# ── the happy path, as a host experiences it ──────────────────────────
def test_preflight_records_and_postflight_clears(tmp_path):
    doc = lifecycle.preflight(
        task="修复 cache key 碰撞", cwd=str(tmp_path), session_id="ses-host-1"
    )

    entry = pending.find("ses-host-1")
    assert entry is not None, "an open loop must be findable by session alone"
    assert entry["loop_id"] == doc["loop_id"]
    assert entry["task"] == "修复 cache key 碰撞"

    lifecycle.postflight(
        task_id=doc["task_id"], loop_id=doc["loop_id"], session_id="ses-host-1", cwd=str(tmp_path)
    )

    assert pending.find("ses-host-1") is None
    assert pending.summary()["outstanding"] == 0


def test_a_run_that_never_reports_back_stays_visible(tmp_path):
    """This is the whole point: the leftover *is* the signal.

    Before this module the directory existed and nothing wrote to it, so a host
    that died mid-run left no trace and the gap looked like "there is no data".
    """
    lifecycle.preflight(task="半途而废", cwd=str(tmp_path), session_id="ses-crash")

    report = pending.summary()
    assert report["outstanding"] == 1
    assert report["oldest_hours"] >= 0
    assert pending.list_pending()[0]["session_id"] == "ses-crash"


def test_a_loop_always_has_a_session_key(tmp_path):
    """Even a host-named-less call: the engine assigns one, so the lookup works.

    Since P5 a loop decides its session id once, at preflight. That is what makes
    an idle event with only a sessionID enough to close a run — including for a
    caller that never thought about sessions at all.
    """
    doc = lifecycle.preflight(task="没有 session 的调用", cwd=str(tmp_path))

    assert doc["session_id"]
    entry = pending.find(doc["session_id"])
    assert entry and entry["loop_id"] == doc["loop_id"]


def test_a_record_needs_a_session_to_exist():
    """The module's own boundary: nothing findable is written without a key."""
    assert pending.record(session_id="", loop_id="LOOP-1") is None
    assert pending.list_pending() == []


# ── robustness at the boundary ─────────────────────────────────────────
def test_a_hostile_session_id_cannot_escape_the_directory(tmp_path):
    lifecycle.preflight(task="路径穿越尝试", cwd=str(tmp_path), session_id="../../etc/passwd")

    written = list(_pending_dir().glob("pending-*.json"))
    assert len(written) == 1
    assert written[0].parent == _pending_dir()
    assert ".." not in written[0].name and "/" not in written[0].name


def test_an_unreadable_record_is_reported_not_resurrected(tmp_path):
    pending.record(session_id="ses-broken", loop_id="LOOP-1", task="x")
    path = pending.path_for("ses-broken")
    path.write_text("{not json", encoding="utf-8")

    assert pending.find("ses-broken") is None
    report = pending.summary()
    assert report["outstanding"] == 1
    assert report["unreadable"] == 1


def test_clear_is_honest_about_whether_something_was_there(tmp_path):
    pending.record(session_id="ses-x", loop_id="LOOP-X")

    assert pending.clear("ses-x") is True
    assert pending.clear("ses-x") is False


def test_a_second_preflight_for_one_session_replaces_the_record(tmp_path):
    """One session, one open loop: the older run's loop state is still on disk."""
    pending.record(session_id="ses-re", loop_id="LOOP-OLD", task="first")
    pending.record(session_id="ses-re", loop_id="LOOP-NEW", task="second")

    assert pending.find("ses-re")["loop_id"] == "LOOP-NEW"
    assert pending.summary()["outstanding"] == 1


# ── what the plugin actually has to work with ──────────────────────────
def test_the_contract_gives_the_plugin_everything_it_needs(tmp_path):
    """Preflight response → sessionID; idle event → sessionID; that must be enough.

    The plugin never sees a loop id except through the preflight document, so if
    the response ever stopped carrying `session_id` the reverse lookup would break
    silently at the far end.
    """
    pre = lifecycle.preflight(
        task="插件只拿得到 sessionID", cwd=str(tmp_path), session_id="ses-plugin-1"
    )
    assert set(["session_id", "loop_id", "task_id"]) <= set(pre)

    # The event handler's whole input, simulated:
    event = {"type": "session.idle", "properties": {"sessionID": pre["session_id"]}}
    entry = pending.find(event["properties"]["sessionID"])
    assert entry and entry["loop_id"] == pre["loop_id"]

    post = lifecycle.postflight(
        task_id=entry["task_id"],
        loop_id=entry["loop_id"],
        session_id=event["properties"]["sessionID"],
        cwd=str(tmp_path),
        outcome="failure",
        quality_score=0.0,
    )
    assert post["learning"]["needs_review"] is False
    assert pending.find(event["properties"]["sessionID"]) is None
