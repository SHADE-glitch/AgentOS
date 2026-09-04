#!/usr/bin/env python3
"""
Failure Detector — Phase 10: Autonomous Recovery Loop

Analyzes Audit output from Phase 9 hooks and produces RecoveryEvents.

Input sources:
  - TeamResult validation (team_result_validator.py)
  - Evidence collector (evidence_collector.py)
  - Retrieval audit (retrieval_audit.py)
  - Runtime execution result (exec_result from loop_controller)

Output:
  - List of RecoveryEvent dicts with: type, source, evidence, severity, recommended_action

Failure types detected:
  - missing_evidence      — no evidence file for a task
  - failed_validation     — TeamResult validator found issues
  - failed_tests          — test exit_code != 0
  - incomplete_teamresult — TeamResult missing required fields
  - memory_claim_invalid  — claims "memory influenced" but no retrieval artifact
  - runtime_error         — runtime execution returned error status

Severity levels:
  - critical  — must recover (blocks final result)
  - high      — should recover (degrades evidence quality)
  - medium    — can recover (cosmetic / optional)
  - low       — informational only
"""

import os
import json
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
REPORTS_DIR = os.path.join(BASE, "reports")


def _session_id():
    return os.environ.get("AOS_SESSION_ID", datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S"))


def _session_dir(session=None):
    sid = session or _session_id()
    return os.path.join(REPORTS_DIR, sid)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def detect_failures(task_id, loop_id="", session=None, session_id="", runtime_result=None,
                    team_result=None, validation_result=None):
    """
    Detect all failures from audit evidence and runtime state.

    Args:
        task_id: str — task identifier
        loop_id: str — loop execution identifier
        session: str — optional session override (legacy)
        session_id: str — Phase 10.5: unified session ID
        runtime_result: dict — exec_result from loop_controller runtime stage
        team_result: dict — TeamResult data (from aggregator)
        validation_result: dict — validation result from team_result_validator

    Returns:
        list of RecoveryEvent dicts
    """
    events = []
    now = _now_iso()
    session_dir = _session_dir(session_id or session)

    # ── 1. Check for missing evidence file ──
    evidence_path = os.path.join(session_dir, f"evidence-{task_id}.json")
    evidence = _load_json(evidence_path)
    if not evidence:
        events.append({
            "type": "missing_evidence",
            "source": "evidence_collector",
            "evidence": {"evidence_path": evidence_path},
            "severity": "high",
            "recommended_action": "collect_evidence",
            "detected_at": now,
            "task_id": task_id,
            "loop_id": loop_id,
        })

    # ── 2. Check runtime execution result ──
    if runtime_result:
        status = runtime_result.get("status", "")
        error = runtime_result.get("error", "")

        if status == "error" or status == "failed":
            events.append({
                "type": "runtime_error",
                "source": "runtime_execute",
                "evidence": {
                    "status": status,
                    "error": error,
                    "execution_id": runtime_result.get("execution_id", ""),
                },
                "severity": "critical",
                "recommended_action": "retry_execution",
                "detected_at": now,
                "task_id": task_id,
                "loop_id": loop_id,
            })

        if status == "partial":
            events.append({
                "type": "runtime_error",
                "source": "runtime_execute",
                "evidence": {
                    "status": status,
                    "error": error,
                    "execution_id": runtime_result.get("execution_id", ""),
                },
                "severity": "high",
                "recommended_action": "retry_execution",
                "detected_at": now,
                "task_id": task_id,
                "loop_id": loop_id,
            })

    # ── 3. Check test results from evidence ──
    if evidence:
        after = evidence.get("after", {})
        test_exit = after.get("test_exit_code")
        test_command = after.get("test_command", "")
        if test_exit is not None and test_exit != 0:
            events.append({
                "type": "failed_tests",
                "source": "evidence_collector",
                "evidence": {
                    "test_command": test_command,
                    "test_exit_code": test_exit,
                    "test_stdout": after.get("test_stdout", "")[:500],
                    "test_stderr": after.get("test_stderr", "")[:500],
                },
                "severity": "critical",
                "recommended_action": "inspect_and_retry",
                "detected_at": now,
                "task_id": task_id,
                "loop_id": loop_id,
            })

    # ── 4. Check TeamResult validation ──
    if validation_result is None:
        # Try to load from file
        validation_path = os.path.join(session_dir, "team-result-validation.json")
        vr = _load_json(validation_path)
        if vr and vr.get("validations"):
            validation_result = vr["validations"][-1] if vr["validations"] else None

    if validation_result:
        if not validation_result.get("valid", True):
            issues = validation_result.get("issues", [])
            events.append({
                "type": "failed_validation",
                "source": "team_result_validator",
                "evidence": {
                    "issues": issues,
                    "checks": validation_result.get("checks", []),
                    "check_summary": validation_result.get("check_summary", {}),
                },
                "severity": "high",
                "recommended_action": "resolve_validation_issues",
                "detected_at": now,
                "task_id": task_id,
                "loop_id": loop_id,
            })

        # Check specific claims
        for check in validation_result.get("checks", []):
            if check.get("check") == "tested_claim" and check.get("status") == "fail":
                events.append({
                    "type": "missing_evidence",
                    "source": "team_result_validator",
                    "evidence": {"detail": check.get("detail", "")},
                    "severity": "high",
                    "recommended_action": "collect_test_evidence",
                    "detected_at": now,
                    "task_id": task_id,
                    "loop_id": loop_id,
                })
            if check.get("check") == "memory_influenced_claim" and check.get("status") == "fail":
                events.append({
                    "type": "memory_claim_invalid",
                    "source": "team_result_validator",
                    "evidence": {"detail": check.get("detail", "")},
                    "severity": "medium",
                    "recommended_action": "retrieve_memory_again",
                    "detected_at": now,
                    "task_id": task_id,
                    "loop_id": loop_id,
                })

    # ── 5. Check TeamResult completeness ──
    if team_result:
        if isinstance(team_result, dict):
            tr = team_result.get("team_result", team_result)
        else:
            tr = {}

        if not tr.get("summary"):
            if not tr.get("lead_output", {}).get("output"):
                events.append({
                    "type": "incomplete_teamresult",
                    "source": "team_result_validator",
                    "evidence": {"missing": "summary or lead_output"},
                    "severity": "medium",
                    "recommended_action": "regenerate_team_result",
                    "detected_at": now,
                    "task_id": task_id,
                    "loop_id": loop_id,
                })

    # ── 6. Sort by severity ──
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    events.sort(key=lambda e: severity_order.get(e.get("severity", "low"), 99))

    return events


def has_critical_failures(events):
    """Check if any event has critical severity."""
    return any(e.get("severity") == "critical" for e in events)


def has_recoverable_failures(events):
    """Check if any event is recoverable (critical or high)."""
    return any(e.get("severity") in ("critical", "high") for e in events)


def summarize_failures(events):
    """Generate a human-readable summary of failures."""
    if not events:
        return "No failures detected."

    lines = [f"Detected {len(events)} failure(s):"]
    for e in events:
        lines.append(f"  [{e['severity'].upper()}] {e['type']}: {e.get('recommended_action', 'N/A')}")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 failure_detector.py <task_id> [loop_id] [session]")
        sys.exit(1)

    task_id = sys.argv[1]
    loop_id = sys.argv[2] if len(sys.argv) > 2 else ""
    session = sys.argv[3] if len(sys.argv) > 3 else None

    events = detect_failures(task_id, loop_id=loop_id, session=session)
    print(json.dumps(events, indent=2, ensure_ascii=False))
    print(f"\n{summarize_failures(events)}")