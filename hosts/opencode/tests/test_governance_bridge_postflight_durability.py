#!/usr/bin/env python3
"""
Governance Bridge — Durable Idempotent Postflight Regression Tests (Agent OS Repair #2)

Regression test for the production-observation finding that postflight was
permanently lost when the host process died mid-postflight (PO-14/PO-17:
governance_postflight_completed missing, loop stuck pending forever).

The repair:
  1. The host plugin writes a DURABLE pending-postflight marker BEFORE spawning
     the postflight bridge, so a process death leaves a resumable record.
  2. run_postflight is IDEMPOTENT: an already-finalized loop is never finalized
     twice (no duplicate evidence_after, no duplicate final status).
  3. resume_pending_postflights() completes markers left by crashed processes;
     markers owned by a LIVE pid are skipped.

These tests exercise real state transitions (marker + loop yaml files), not
mocked functions. Only the external side effects (evidence collection, failure
detection, recovery planning) are replaced by recorders so no real ~/.agents
state or reports are touched.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, "/home/shade/.agents/runtime")
sys.path.insert(0, "/home/shade/.agents/runtime/loop-controller")
sys.path.insert(0, "/home/shade/.agents/runtime/audit")
sys.path.insert(0, "/home/shade/.agents/runtime/recovery")

import pytest
import yaml

import governance_bridge as gb


# ── fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point STATE_DIR/PENDING_DIR at temp dirs and stub external side effects."""
    state_dir = tmp_path / "state"
    pending_dir = tmp_path / "pending-postflight"
    state_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(gb, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(gb, "PENDING_DIR", str(pending_dir))

    calls = {"evidence_after": 0}

    import audit_integration

    def fake_evidence_after(*a, **kw):
        calls["evidence_after"] += 1
        return os.path.join(str(tmp_path), "evidence-after.json")

    monkeypatch.setattr(audit_integration, "collect_task_evidence_after", fake_evidence_after)

    import failure_detector
    import recovery_planner
    import retry_controller

    monkeypatch.setattr(failure_detector, "detect_failures", lambda *a, **kw: [])
    monkeypatch.setattr(recovery_planner, "plan_recovery", lambda *a, **kw: {"plan": "none"})
    monkeypatch.setattr(retry_controller, "get_retry_count", lambda *a, **kw: 0)
    return {"state_dir": str(state_dir), "pending_dir": str(pending_dir), "calls": calls}


def _write_loop_state(state_dir, loop_id, stage="preflight", final="pending"):
    path = os.path.join(state_dir, f"{loop_id}.yaml")
    state = {
        "loop_id": loop_id,
        "task_id": f"TASK-{loop_id}",
        "session_id": "ses-test",
        "current_stage": stage,
        "final_status": final,
        "evidence_before": {"project_root": "/tmp", "repo_resolved": True},
    }
    with open(path, "w") as f:
        yaml.dump(state, f)
    return path


def _read_loop_state(state_dir, loop_id):
    with open(os.path.join(state_dir, f"{loop_id}.yaml")) as f:
        return yaml.safe_load(f)


def _read_marker(pending_dir, loop_id):
    path = os.path.join(pending_dir, f"{loop_id}.json")
    assert os.path.exists(path), f"marker missing: {path}"
    with open(path) as f:
        return json.load(f)


# ── TEST 1: normal completion → postflight completed ─────────────

def test_normal_completion_finalizes_loop(isolated):
    loop_id = "LOOP-NORMAL"
    _write_loop_state(isolated["state_dir"], loop_id)

    result = gb.run_postflight("TASK-X", loop_id, "ses-test", "/tmp")

    assert result["final_status"] == "completed"
    assert result["replayed"] is False
    assert result["evidence_path"].endswith("evidence-after.json")

    state = _read_loop_state(isolated["state_dir"], loop_id)
    assert state["current_stage"] == "postflight"
    assert state["final_status"] == "completed"
    assert state["completed_at"]

    marker = _read_marker(isolated["pending_dir"], loop_id)
    assert marker["status"] == "completed"
    assert marker["loop_id"] == loop_id
    assert isolated["calls"]["evidence_after"] == 1


# ── TEST 2: duplicate recovery → NO double finalization ─────────

def test_duplicate_run_postflight_is_idempotent(isolated):
    loop_id = "LOOP-DUP"
    _write_loop_state(isolated["state_dir"], loop_id)

    first = gb.run_postflight("TASK-X", loop_id, "ses-test", "/tmp")
    completed_at_first = _read_loop_state(isolated["state_dir"], loop_id)["completed_at"]

    # Duplicate trigger (e.g. session.idle + dispose both firing, or a resume
    # racing a normal trigger): the second call must replay, not re-finalize.
    second = gb.run_postflight("TASK-X", loop_id, "ses-test", "/tmp")

    assert first["final_status"] == "completed"
    assert second["replayed"] is True
    assert second["final_status"] == "completed"
    assert isolated["calls"]["evidence_after"] == 1  # collected exactly once

    state = _read_loop_state(isolated["state_dir"], loop_id)
    assert state["completed_at"] == completed_at_first  # not rewritten


# ── TEST 3: crash mid-postflight → marker survives → resume completes ─

def test_resume_completes_interrupted_postflight(isolated):
    loop_id = "LOOP-CRASH"
    _write_loop_state(isolated["state_dir"], loop_id)

    # Simulate: host plugin claimed the marker (running, dead pid) then died
    # before the bridge returned. The loop is NOT yet finalized.
    gb.upsert_pending_marker(
        task_id="TASK-X", loop_id=loop_id, session_id="ses-test", cwd="/tmp",
        status="running",
    )
    marker = _read_marker(isolated["pending_dir"], loop_id)
    marker["pid"] = 999999  # dead process
    marker["status"] = "running"
    gb._write_marker(loop_id, marker)

    # Pre-resume state: loop still at preflight/pending.
    assert _read_loop_state(isolated["state_dir"], loop_id)["final_status"] == "pending"

    results = gb.resume_pending_postflights()

    assert len(results) == 1
    assert results[0]["loop_id"] == loop_id
    assert results[0]["status"] == "completed"

    state = _read_loop_state(isolated["state_dir"], loop_id)
    assert state["current_stage"] == "postflight"
    assert state["final_status"] == "completed"
    assert state["completed_at"]
    assert isolated["calls"]["evidence_after"] == 1

    marker = _read_marker(isolated["pending_dir"], loop_id)
    assert marker["status"] == "completed"


# ── TEST 4: resume never double-finalizes an already-completed loop ─

def test_resume_skips_completed_markers(isolated):
    loop_id = "LOOP-DONE"
    _write_loop_state(isolated["state_dir"], loop_id)
    gb.run_postflight("TASK-X", loop_id, "ses-test", "/tmp")
    assert isolated["calls"]["evidence_after"] == 1

    results = gb.resume_pending_postflights()

    assert results == []  # completed marker → skipped, nothing re-run
    assert isolated["calls"]["evidence_after"] == 1


# ── TEST 5: live marker owned by another pid is NOT stolen ───────

def test_resume_skips_live_markers(isolated):
    loop_id = "LOOP-LIVE"
    _write_loop_state(isolated["state_dir"], loop_id)

    gb.upsert_pending_marker(
        task_id="TASK-X", loop_id=loop_id, session_id="ses-test", cwd="/tmp",
        status="running",
    )
    marker = _read_marker(isolated["pending_dir"], loop_id)
    marker["pid"] = os.getpid()  # this process is still alive → not resumable
    gb._write_marker(loop_id, marker)

    results = gb.resume_pending_postflights()

    assert len(results) == 1
    assert results[0]["status"] == "skipped_active"
    assert isolated["calls"]["evidence_after"] == 0
    assert _read_loop_state(isolated["state_dir"], loop_id)["final_status"] == "pending"


# ── TEST 6: failed attempt is retried by resume (bounded) ────────

def test_resume_retries_failed_attempts(isolated):
    loop_id = "LOOP-FAIL"
    _write_loop_state(isolated["state_dir"], loop_id)

    # First attempt fails inside the bridge (failure detection raises — this is
    # NOT swallowed, so the wrapper marks the marker failed and re-raises).
    import failure_detector as fd

    def failing_detect(*a, **kw):
        raise RuntimeError("bridge crashed mid-postflight")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(fd, "detect_failures", failing_detect)

    try:
        with pytest.raises(RuntimeError):
            gb.run_postflight("TASK-X", loop_id, "ses-test", "/tmp")
    finally:
        monkeypatch.undo()

    marker = _read_marker(isolated["pending_dir"], loop_id)
    assert marker["status"] == "failed"
    assert marker["attempts"] == 1
    assert marker["last_error"]

    # Restore a working bridge; resume must retry and complete.
    import failure_detector as fd2

    monkeypatch2 = pytest.MonkeyPatch()
    monkeypatch2.setattr(fd2, "detect_failures", lambda *a, **kw: [])
    try:
        results = gb.resume_pending_postflights()
    finally:
        monkeypatch2.undo()

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    state = _read_loop_state(isolated["state_dir"], loop_id)
    assert state["final_status"] == "completed"
    assert state["current_stage"] == "postflight"
    # Evidence is collected on the failed attempt AND the successful retry; the
    # guarantee under test is that finalization happened exactly once (the
    # retry did collect). A second resume must not collect again.
    assert isolated["calls"]["evidence_after"] >= 2
    after_retry = isolated["calls"]["evidence_after"]
    assert gb.resume_pending_postflights() == []
    assert isolated["calls"]["evidence_after"] == after_retry
