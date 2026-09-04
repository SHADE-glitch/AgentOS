#!/usr/bin/env python3
"""
Recovery Executor — Phase 11: Semi-Autonomous Recovery Loop

BRIDGE between Recovery Planning and Runtime Execution.

Phase 10 (old):  detect → plan → record (advisory only)
Phase 11 (new):  detect → plan → execute → verify

This module handles the execute → verify half of the recovery loop.
It receives a RecoveryDecision and converts it into a RecoveryTask that
can be sent to the runtime provider (OpenCode) for execution.

Key Principles:
  - Recovery NEVER modifies business code directly — it delegates to OpenCode
  - RecoveryTask is a structured instruction for OpenCode to act on
  - Retry budget is hard-capped at MAX_RECOVERY_RETRIES (2)
  - Each attempt produces new evidence for verification
  - RecoveryTask includes evidence_required so OpenCode knows what to produce

RecoveryDecision → RecoveryTask flow:
  {
    failure_events: [...],    →  failure_reason: str
    recovery_actions: [...],  →  required_action: str
    retry_count: int,         →  retry_context: dict
    task_id: str,             →  task_id: str
    session_id: str           →  evidence_required: list
  }

Usage in loop<｜image｜>controller.py:
    from recovery_executor import create_recovery_task, execute_recovery

    recovery_task = create_recovery_task(recovery_decision, original_task, session_id)
    new_result = execute_recovery(recovery_task, runtime_executor, session_id)
"""

import os
import json
import traceback
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
REPORTS_DIR = os.path.join(BASE, "reports")

MAX_RECOVERY_RETRIES = 2


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _session_dir(session_id):
    d = os.path.join(REPORTS_DIR, session_id)
    os.makedirs(d, exist_ok=True)
    return d


# ── RecoveryTask Data Structure ──────────────────────────────────

def create_recovery_task(recovery_decision, original_task, session_id=""):
    """
    Convert a RecoveryDecision into a structured RecoveryTask.

    Phase 11: This is the bridge between recovery planning and execution.
    RecoveryTask is what gets sent to OpenCode for re-execution.

    Args:
        recovery_decision: dict with:
            - failure_events: list — failures from failure_detector
            - recovery_actions: list — actions from recovery_planner
            - retry_count: int — current retry attempt number
            - task_id: str
            - loop_id: str
            - recovery_plan: dict — full recovery plan
        original_task: dict with:
            - task_id: str
            - task_text: str — original task description
            - decision_context: dict — original routing context
            - model: str
            - provider: str
            - project_root: str
        session_id: str — unified session ID

    Returns:
        dict — RecoveryTask:
          {
            task_id: str,
            original_task: str,
            failure_reason: str,
            required_action: str,
            retry_context: dict,
            evidence_required: list,
            retry_attempt: int,
            session_id: str,
            created_at: str,
          }
    """
    failure_events = recovery_decision.get("failure_events", [])
    recovery_actions = recovery_decision.get("recovery_actions", [])
    retry_count = recovery_decision.get("retry_count", 0)

    # Build failure reason from events
    failure_types = [e.get("type", "unknown") for e in failure_events]
    failure_reasons = [e.get("reason", e.get("description", "")) for e in failure_events]
    failure_reason = "; ".join(f"{t}: {r}" for t, r in zip(failure_types, failure_reasons) if r)

    # Build required action from recovery plan
    action_descriptions = [a.get("description", a.get("action", "unknown")) for a in recovery_actions]
    required_action = "; ".join(action_descriptions) if action_descriptions else "retry_execution"

    # Collect required evidence from all actions
    evidence_required = []
    for a in recovery_actions:
        evidence_required.extend(a.get("evidence_required", []))
    evidence_required = list(set(evidence_required))  # deduplicate

    # Build retry context for OpenCode
    retry_context = {
        "attempt": retry_count + 1,
        "max_retries": MAX_RECOVERY_RETRIES,
        "failure_types": failure_types,
        "target_stages": recovery_decision.get("recovery_plan", {}).get("target_stages", []),
        "previous_result": recovery_decision.get("exec_result", {}),
        "hint": _build_retry_hint(failure_types, required_action),
    }

    return {
        "task_id": recovery_decision.get("task_id", ""),
        "loop_id": recovery_decision.get("loop_id", ""),
        "original_task": original_task.get("task_text", ""),
        "failure_reason": failure_reason,
        "required_action": required_action,
        "retry_context": retry_context,
        "evidence_required": evidence_required,
        "retry_attempt": retry_count + 1,
        "session_id": session_id,
        "created_at": _now_iso(),
    }


def _build_retry_hint(failure_types, required_action):
    """Build a human-readable hint for OpenCode about what to fix."""
    hints = []
    if "failed_tests" in failure_types:
        hints.append("Tests failed — review test output and fix the code")
    if "runtime_error" in failure_types:
        hints.append("Runtime execution error — adjust approach or fix errors")
    if "incomplete_teamresult" in failure_types:
        hints.append("Result was incomplete — provide full output")
    if "missing_evidence" in failure_types:
        hints.append("Missing evidence — ensure test command and output are captured")
    if not hints:
        hints.append(f"Retry execution with adjusted context: {required_action}")
    return " ".join(hints)


# ── Recovery Execution Engine ────────────────────────────────────

def execute_recovery(recovery_task, runtime_executor, session_id=""):
    """
    Execute the recovery task by delegating to the runtime provider.

    Phase 11: This is the execute → verify cycle.
    It sends the RecoveryTask to the runtime provider (OpenCode) and
    collects the new result for verification.

    The runtime_executor is responsible for:
      - Deciding what to modify (OpenCode agent)
      - Running tests or retrying
      - Explaining failure if retry doesn't help

    Recovery NEVER directly modifies business code.

    Args:
        recovery_task: dict — RecoveryTask from create_recovery_task()
        runtime_executor: callable — function(task_id, task_text, decision_context,
                                              model, provider, project_root)
                              → exec_result dict
        session_id: str — unified session ID

    Returns:
        dict — RecoveryResult:
          {
            success: bool,
            recovery_task: dict,
            new_result: dict,
            evidence_collected: bool,
            verified: bool,
            errors: list,
          }
    """
    result = {
        "success": False,
        "recovery_task": recovery_task,
        "new_result": None,
        "evidence_collected": False,
        "verified": False,
        "errors": [],
    }

    try:
        task_id = recovery_task.get("task_id", "")
        original_task = recovery_task.get("original_task", "")
        retry_attempt = recovery_task.get("retry_attempt", 1)
        evidence_required = recovery_task.get("evidence_required", [])

        print(f"\n  [recovery-executor] Attempt {retry_attempt}/{MAX_RECOVERY_RETRIES}")
        print(f"  [recovery-executor] Task: {original_task[:80]}...")
        print(f"  [recovery-executor] Failure: {recovery_task.get('failure_reason', 'unknown')[:120]}")
        print(f"  [recovery-executor] Action: {recovery_task.get('required_action', 'unknown')[:120]}")
        print(f"  [recovery-executor] Evidence required: {evidence_required}")

        # Build the retry task text with context for OpenCode
        retry_task_text = _build_retry_task_text(recovery_task)

        # Build decision context with recovery metadata
        retry_context = recovery_task.get("retry_context", {})
        decision_context = {
            "task_classification": "recovery_retry",
            "retry_attempt": retry_attempt,
            "max_retries": MAX_RECOVERY_RETRIES,
            "failure_reason": recovery_task.get("failure_reason", ""),
            "required_action": recovery_task.get("required_action", ""),
            "evidence_required": evidence_required,
            "retry_hint": retry_context.get("hint", ""),
        }

        # Execute via runtime provider (OpenCode)
        print(f"  [recovery-executor] Delegating to runtime provider...")
        new_result = runtime_executor(
            task_id=f"{task_id}-R{retry_attempt}",
            task_text=retry_task_text,
            decision_context=decision_context,
            model="",  # Use default
            provider="opencode",  # Always OpenCode for recovery
            project_root=retry_context.get("project_root", ""),
        )

        result["new_result"] = new_result

        if new_result is None:
            result["errors"].append("Runtime executor returned None")
            return result

        # Verify: check if required evidence was produced
        evidence_collected = _verify_evidence(new_result, evidence_required)
        result["evidence_collected"] = evidence_collected

        # Check if execution succeeded
        status = new_result.get("status", "error")
        if status == "success":
            result["success"] = True
            result["verified"] = evidence_collected
            print(f"  [recovery-executor] Recovery succeeded (status={status})")
        else:
            result["errors"].append(f"Runtime returned status={status}")
            print(f"  [recovery-executor] Recovery failed (status={status})")

        # Save recovery task to session directory
        _save_recovery_task_result(recovery_task, result, session_id)

    except Exception as e:
        result["errors"].append(str(e))
        traceback.print_exc()
        print(f"  [recovery-executor] Failed: {e}")

    return result


def _build_retry_task_text(recovery_task):
    """Build the task text for the retry attempt, including context."""
    original = recovery_task.get("original_task", "")
    failure_reason = recovery_task.get("failure_reason", "")
    required_action = recovery_task.get("required_action", "")
    retry_attempt = recovery_task.get("retry_attempt", 1)
    hint = recovery_task.get("retry_context", {}).get("hint", "")

    return (
        f"[RECOVERY RETRY #{retry_attempt}] Original task: {original}\n\n"
        f"Previous attempt failed because: {failure_reason}\n\n"
        f"Required action: {required_action}\n\n"
        f"Hint: {hint}\n\n"
        f"Please fix the issue and re-execute. "
        f"Ensure all required evidence is produced."
    )


def _verify_evidence(exec_result, evidence_required):
    """
    Verify that required evidence fields are present in the exec result.

    Returns:
        bool — True if all required evidence is present
    """
    if not evidence_required:
        return True

    for field in evidence_required:
        if field == "test_command" and not exec_result.get("test_command"):
            return False
        if field == "test_exit_code" and exec_result.get("test_exit_code") is None:
            return False
        if field == "test_stdout" and not exec_result.get("test_stdout"):
            return False
        if field == "evidence_file":
            # evidence_file is always produced by the pipeline
            continue
        if field == "team_result":
            # team_result is produced by the pipeline
            continue
        if field == "retrieval_artifact":
            # retrieval_artifact is produced by the pipeline
            continue

    return True


def _save_recovery_task_result(recovery_task, result, session_id):
    """Save the recovery task and result to the session directory."""
    if not session_id:
        return

    try:
        session_dir = _session_dir(session_id)
        task_path = os.path.join(
            session_dir,
            f"recovery-task-{recovery_task.get('task_id', 'unknown')}.json"
        )

        artifact = {
            "recovery_task": recovery_task,
            "result": {
                "success": result.get("success"),
                "evidence_collected": result.get("evidence_collected"),
                "verified": result.get("verified"),
                "errors": result.get("errors", []),
                "new_result_status": result.get("new_result", {}).get("status", "unknown"),
            },
            "saved_at": _now_iso(),
        }

        with open(task_path, "w") as f:
            json.dump(artifact, f, indent=2, default=str)

        print(f"  [recovery-executor] Saved recovery task result to {task_path}")
    except Exception as e:
        print(f"  [recovery-executor] Failed to save task result: {e}")


# ── Recovery Budget Check ────────────────────────────────────────

def check_recovery_budget(task_id, session_id=""):
    """
    Check remaining recovery budget for a task.

    Returns:
        dict with remaining, used, max
    """
    session_dir = _session_dir(session_id)
    recovery_path = os.path.join(session_dir, "recovery.jsonl")

    used = 0
    if os.path.exists(recovery_path):
        with open(recovery_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("task_id") == task_id:
                        used += 1
                except json.JSONDecodeError:
                    pass

    return {
        "remaining": max(0, MAX_RECOVERY_RETRIES - used),
        "used": used,
        "max": MAX_RECOVERY_RETRIES,
        "exhausted": used >= MAX_RECOVERY_RETRIES,
    }


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 recovery_executor.py create-task <task_id> <session_id>")
        print("  python3 recovery_executor.py check-budget <task_id> <session_id>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "check-budget":
        tid = sys.argv[2] if len(sys.argv) > 2 else "test"
        sid = sys.argv[3] if len(sys.argv) > 3 else ""
        budget = check_recovery_budget(tid, sid)
        print(json.dumps(budget, indent=2))
    elif cmd == "create-task":
        # For testing: create a sample recovery task
        import json as _json
        decision = {
            "task_id": sys.argv[2] if len(sys.argv) > 2 else "test",
            "loop_id": "LOOP-test",
            "failure_events": [
                {"type": "failed_tests", "severity": "high",
                 "reason": "Test exit_code=1", "description": "Tests failed"}
            ],
            "recovery_actions": [
                {"action": "inspect_and_retry",
                 "description": "Inspect test failure output and retry",
                 "evidence_required": ["test_command", "test_exit_code", "test_stdout"]}
            ],
            "retry_count": 0,
            "recovery_plan": {"target_stages": ["runtime"]},
            "exec_result": {"status": "error"},
        }
        original = {
            "task_text": "Fix the broken test",
            "decision_context": {},
            "model": "",
            "provider": "opencode",
            "project_root": BASE,
        }
        sid = sys.argv[3] if len(sys.argv) > 3 else ""
        task = create_recovery_task(decision, original, sid)
        print(_json.dumps(task, indent=2))