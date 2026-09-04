#!/usr/bin/env python3
"""
Retry Controller — Phase 10: Autonomous Recovery Loop

Controls limited retry execution with safety constraints.

Constraints:
  - Maximum 2 retries total (hard limit)
  - No infinite loops
  - No auto-modification of business code
  - Each retry attempt requires an evidence delta
  - Retry exhaustion must be recorded

Flow:
  Attempt 1
    ↓
  Audit (failure detection)
    ↓
  Recovery Plan (if failures detected)
    ↓
  Attempt 2 (if retry budget remains)
    ↓
  Audit again
    ↓
  Final Result (with or without recovery)
"""

import os
import json
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
REPORTS_DIR = os.path.join(BASE, "reports")

MAX_RETRIES = 2


def _session_id():
    return os.environ.get("AOS_SESSION_ID", datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S"))


def _session_dir(session=None):
    sid = session or _session_id()
    d = os.path.join(REPORTS_DIR, sid)
    os.makedirs(d, exist_ok=True)
    return d


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def should_retry(recovery_plan, retry_count):
    """
    Determine whether a retry should be attempted.

    Args:
        recovery_plan: dict — from recovery_planner.plan_recovery()
        retry_count: int — current retry count (0-indexed, 0 = first attempt, 1 = one retry done)

    Returns:
        (bool, str) — (should_retry, reason)
    """
    if not recovery_plan:
        return False, "No recovery plan"

    if not recovery_plan.get("recovery_needed", False):
        return False, "No recovery needed"

    if not recovery_plan.get("can_recover", False):
        return False, "No recoverable actions in plan"

    if recovery_plan.get("retry_exhausted", False):
        return False, "Retry budget exhausted"

    if retry_count >= MAX_RETRIES:
        return False, f"Retry limit exceeded ({MAX_RETRIES})"

    # Check if any actionable actions have retry budget
    actionable = recovery_plan.get("actionable_actions", [])
    if not actionable:
        return False, "No actionable recovery actions"

    return True, f"Retry {retry_count + 1}/{MAX_RETRIES}"


def record_retry_attempt(task_id, loop_id, attempt_number, recovery_plan,
                         failure_events, result=None, session=None, session_id=""):
    """
    Record a retry attempt to the recovery log.

    Args:
        task_id: str
        loop_id: str
        attempt_number: int — 1-based attempt number
        recovery_plan: dict — the recovery plan used
        failure_events: list — the failures that triggered this retry
        result: dict — optional, result of the retry attempt
        session: str — optional session ID (legacy)
        session_id: str — Phase 10.5: unified session ID

    Returns:
        str — path to recovery log
    """
    session_dir = _session_dir(session_id or session)
    recovery_path = os.path.join(session_dir, "recovery.jsonl")

    entry = {
        "task_id": task_id,
        "loop_id": loop_id,
        "attempt": attempt_number,
        "timestamp": _now_iso(),
        "trigger_failures": [
            {"type": e.get("type", ""), "severity": e.get("severity", "")}
            for e in (failure_events or [])
        ],
        "recovery_actions": [
            a.get("action", "") for a in recovery_plan.get("actions", [])
        ],
        "target_stages": recovery_plan.get("target_stages", []),
        "result": result or {},
    }

    with open(recovery_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return recovery_path


def get_retry_history(task_id, session=None, session_id=""):
    """
    Read the retry history for a task.

    Returns:
        list of retry entries
    """
    session_dir = _session_dir(session_id or session)
    recovery_path = os.path.join(session_dir, "recovery.jsonl")
    if not os.path.exists(recovery_path):
        return []

    entries = []
    with open(recovery_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("task_id") == task_id:
                    entries.append(entry)
            except json.JSONDecodeError:
                pass
    return entries


def get_retry_count(task_id, session=None, session_id=""):
    """Get the current retry count for a task."""
    return len(get_retry_history(task_id, session, session_id=session_id))


def execute_retry_loop(task_id, loop_id, failure_events, recovery_plan,
                       retry_fn, retry_context=None, session=None, session_id=""):
    """
    Execute a single retry attempt with full recording.

    This is the core retry loop function. It:
      1. Checks if retry is allowed
      2. Records the attempt
      3. Calls retry_fn with recovery context
      4. Returns the result

    Args:
        task_id: str
        loop_id: str
        failure_events: list — failures that triggered retry
        recovery_plan: dict — recovery plan from recovery_planner
        retry_fn: callable — function(attempt_number, recovery_plan, retry_context) → result dict
        retry_context: dict — additional context for the retry function
        session: str — optional session ID (legacy)
        session_id: str — Phase 10.5: unified session ID

    Returns:
        dict with retry_result, attempt_number, success
    """
    retry_count = get_retry_count(task_id, session, session_id=session_id)
    attempt_number = retry_count + 1

    can_retry, reason = should_retry(recovery_plan, retry_count)

    if not can_retry:
        record_retry_attempt(
            task_id, loop_id, attempt_number, recovery_plan,
            failure_events,
            result={"status": "skipped", "reason": reason},
            session_id=session_id,
        )
        return {
            "retry_executed": False,
            "attempt_number": attempt_number,
            "reason": reason,
            "result": None,
        }

    # Record attempt start
    record_retry_attempt(
        task_id, loop_id, attempt_number, recovery_plan,
        failure_events,
        result={"status": "started"},
        session_id=session_id,
    )

    # Execute retry
    try:
        result = retry_fn(attempt_number, recovery_plan, retry_context or {})
    except Exception as e:
        result = {
            "status": "error",
            "error": str(e),
        }

    # Append result to the same entry
    session_dir = _session_dir(session_id or session)
    recovery_path = os.path.join(session_dir, "recovery.jsonl")

    # Read existing entries, update last one
    entries = []
    if os.path.exists(recovery_path):
        with open(recovery_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

    if entries:
        entries[-1]["result"] = result
        entries[-1]["completed_at"] = _now_iso()

    with open(recovery_path, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    return {
        "retry_executed": True,
        "attempt_number": attempt_number,
        "reason": reason,
        "result": result,
    }


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 retry_controller.py history <task_id> [session]")
        print("  python3 retry_controller.py count <task_id> [session]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "history":
        task_id = sys.argv[2] if len(sys.argv) > 2 else ""
        session = sys.argv[3] if len(sys.argv) > 3 else None
        entries = get_retry_history(task_id, session)
        print(json.dumps(entries, indent=2, ensure_ascii=False))

    elif cmd == "count":
        task_id = sys.argv[2] if len(sys.argv) > 2 else ""
        session = sys.argv[3] if len(sys.argv) > 3 else None
        count = get_retry_count(task_id, session)
        print(f"Retry count for {task_id}: {count}/{MAX_RETRIES}")