#!/usr/bin/env python3
"""
Recovery Integration — Phase 10: Autonomous Recovery Loop

Wires the recovery loop into the Agent OS pipeline.

This is the SINGLE entry point for loop_controller.py to invoke
the full recovery flow:

  1. Detect failures from audit evidence
  2. Generate recovery plan
  3. Decide if retry is needed
  4. Execute retry if applicable
  5. Record all recovery state

The recovery loop is inserted AFTER Stage 9 (Reconciler) and
BEFORE Stage 10 (Finalize).

Usage in loop_controller.py:
    from recovery_integration import run_recovery_loop

    recovery_result = run_recovery_loop(
        task_id=task_id,
        loop_id=loop_id,
        state=state,
        exec_result=exec_result,
        team_result=team_result,
        decision_context=decision_context,
        retry_fn=retry_fn,
    )

RecoveryDecision Interface (Phase 10.5 / M-2):
    The recovery loop is designed with a clear interface boundary.
    It does NOT directly re-invoke the OpenCode executor (retry_fn=None).

    The contract is:

      OpenCode Adapter (future)      Recovery Loop (current)
      ─────────────────────────      ────────────────────────
      calls run_recovery_loop()  →   detect_failures()
      reads RecoveryDecision     ←   plan_recovery()
      decides to retry or not    →   record_retry_attempt()
      re-invokes pipeline        →   (never called automatically)

    RecoveryDecision format:
      {
        "recovery_attempted": bool,
        "recovery_success": bool,
        "failures_detected": int,
        "recovery_plan": { "actions": [...], "summary": str },
        "final_status": "completed" | "partial" | "failed",
      }

    To integrate real retry:
      1. Set retry_fn=your_retry_function in the run_recovery_loop() call
      2. your_retry_function receives: (attempt_number, recovery_plan, retry_context)
      3. It returns: {"status": "success" | "error", "output": ...}
"""

import os
import sys
import traceback

BASE = "/home/shade/.agents"
RECOVERY_DIR = os.path.join(BASE, "runtime", "recovery")

if RECOVERY_DIR not in sys.path:
    sys.path.insert(0, RECOVERY_DIR)

from datetime import datetime, timezone

from failure_detector import detect_failures, summarize_failures, has_critical_failures
from recovery_planner import plan_recovery, get_recovery_stages
from retry_controller import (
    should_retry, record_retry_attempt, get_retry_count,
    execute_retry_loop, MAX_RETRIES,
)
from recovery_executor import (
    create_recovery_task, execute_recovery,
    check_recovery_budget, MAX_RECOVERY_RETRIES,
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_recovery_loop(task_id, loop_id, state, exec_result=None,
                      team_result=None, decision_context=None,
                      retry_fn=None, retry_context=None, session_id=""):
    """
    Run the full recovery loop for a single task execution.

    This is called AFTER Stage 9 (Reconciler) and BEFORE Stage 10 (Finalize).

    Args:
        task_id: str
        loop_id: str
        state: dict — the full loop state from loop_controller
        exec_result: dict — runtime execution result
        team_result: dict — TeamResult from collaboration stage
        decision_context: dict — full DecisionContext from retrieval
        retry_fn: callable — function(attempt_number, recovery_plan, retry_context) → dict
        retry_context: dict — additional context for retry function
        session_id: str — Phase 10.5: unified session ID

    Returns:
        dict with:
          - recovery_attempted: bool
          - recovery_success: bool
          - failures_detected: int
          - recovery_plan: dict
          - retry_result: dict
          - final_status: str
    """
    result = {
        "recovery_attempted": False,
        "recovery_success": False,
        "failures_detected": 0,
        "recovery_plan": None,
        "retry_result": None,
        "final_status": "completed",
        "errors": [],
    }

    # Phase 10.5: Extract session_id from state if not provided explicitly
    if not session_id:
        session_id = state.get("session_id", "")

    try:
        # Step 1: Detect failures from audit evidence
        failure_events = detect_failures(
            task_id=task_id,
            loop_id=loop_id,
            session_id=session_id,
            runtime_result=exec_result,
            team_result=team_result,
        )
        result["failures_detected"] = len(failure_events)

        if not failure_events:
            print(f"  [recovery] No failures detected. Skipping recovery loop.")
            return result

        print(f"\n  [recovery] Detected {len(failure_events)} failure(s):")
        for evt in failure_events:
            print(f"    [{evt['severity'].upper()}] {evt['type']} → {evt.get('recommended_action', 'N/A')}")

        # Step 2: Generate recovery plan
        retry_count = get_retry_count(task_id, session_id=session_id)
        recovery_plan = plan_recovery(
            failure_events,
            task_id=task_id,
            loop_id=loop_id,
            retry_count=retry_count,
        )
        result["recovery_plan"] = recovery_plan

        print(f"\n  [recovery] Plan: {recovery_plan.get('summary', 'No plan')}")

        # Step 3: Check if retry is possible
        can_retry, reason = should_retry(recovery_plan, retry_count)
        if not can_retry:
            print(f"  [recovery] Retry not allowed: {reason}")
            result["final_status"] = "partial" if failure_events else "completed"
            # Record exhausted attempt
            record_retry_attempt(
                task_id, loop_id, retry_count + 1,
                recovery_plan, failure_events,
                result={"status": "exhausted", "reason": reason},
                session_id=session_id,
            )
            return result

        # Step 4: Execute retry
        result["recovery_attempted"] = True

        if retry_fn is None:
            print(f"  [recovery] No retry function provided. Skipping retry execution.")
            result["recovery_success"] = False
            result["final_status"] = "partial"
            return result

        retry_result = execute_retry_loop(
            task_id=task_id,
            loop_id=loop_id,
            failure_events=failure_events,
            recovery_plan=recovery_plan,
            retry_fn=retry_fn,
            retry_context=retry_context,
            session_id=session_id,
        )
        result["retry_result"] = retry_result

        if retry_result.get("retry_executed"):
            print(f"  [recovery] Retry attempt {retry_result['attempt_number']} executed")
            retry_status = retry_result.get("result", {}).get("status", "unknown")
            result["recovery_success"] = retry_status == "success"
            result["final_status"] = "completed" if result["recovery_success"] else "partial"
        else:
            print(f"  [recovery] Retry not executed: {retry_result.get('reason', 'unknown')}")
            result["final_status"] = "partial"

    except Exception as e:
        print(f"  [recovery] Recovery loop failed (non-critical): {e}")
        traceback.print_exc()
        result["errors"].append(str(e))
        result["final_status"] = "partial"

    return result


def build_retry_function(loop_controller_retry):
    """
    Build a retry function compatible with the recovery loop.

    This wraps the loop_controller's retry logic so it can be passed
    to run_recovery_loop().

    Args:
        loop_controller_retry: callable — function that takes
            (attempt_number, recovery_plan, retry_context)
            and returns a result dict

    Returns:
        callable suitable for retry_fn parameter
    """
    def retry_fn(attempt_number, recovery_plan, retry_context):
        return loop_controller_retry(attempt_number, recovery_plan, retry_context)
    return retry_fn


# ── Phase 11: Recovery Execution Bridge ──────────────────────────

def run_recovery_loop_with_execution(task_id, loop_id, state, exec_result=None,
                                     team_result=None, decision_context=None,
                                     runtime_executor=None, retry_context=None,
                                     session_id=""):
    """
    Phase 11: Full recovery loop with execute → verify cycle.

    This extends run_recovery_loop() by adding the execution bridge.
    When failures are detected and a recovery plan is generated,
    it creates a RecoveryTask and delegates execution to the
    runtime provider (OpenCode), then collects and verifies new evidence.

    Flow:
      detect → plan → [if recoverable] create RecoveryTask → execute → verify

    Args:
        task_id: str
        loop_id: str
        state: dict — full loop state
        exec_result: dict — original runtime execution result
        team_result: dict — TeamResult data
        decision_context: dict — DecisionContext from retrieval
        runtime_executor: callable — function(task_id, task_text, decision_context,
                                              model, provider, project_root)
                              → exec_result dict
        retry_context: dict — additional context (project_root, etc.)
        session_id: str — unified session ID

    Returns:
        dict with recovery result including execution details
    """
    result = {
        "recovery_attempted": False,
        "recovery_success": False,
        "failures_detected": 0,
        "recovery_plan": None,
        "retry_result": None,
        "execution_result": None,
        "final_status": "completed",
        "errors": [],
    }

    if not session_id:
        session_id = state.get("session_id", "")

    try:
        # ── Step 1: Detect failures ──
        failure_events = detect_failures(
            task_id=task_id,
            loop_id=loop_id,
            session_id=session_id,
            runtime_result=exec_result,
            team_result=team_result,
        )
        result["failures_detected"] = len(failure_events)

        if not failure_events:
            print(f"  [recovery] No failures detected. Skipping recovery loop.")
            return result

        print(f"\n  [recovery] Detected {len(failure_events)} failure(s):")
        for evt in failure_events:
            print(f"    [{evt['severity'].upper()}] {evt['type']} → {evt.get('recommended_action', 'N/A')}")

        # ── Step 2: Generate recovery plan ──
        retry_count = get_retry_count(task_id, session_id=session_id)
        recovery_plan = plan_recovery(
            failure_events,
            task_id=task_id,
            loop_id=loop_id,
            retry_count=retry_count,
        )
        result["recovery_plan"] = recovery_plan

        print(f"\n  [recovery] Plan: {recovery_plan.get('summary', 'No plan')}")

        # ── Step 3: Check retry budget ──
        can_retry, reason = should_retry(recovery_plan, retry_count)
        if not can_retry:
            print(f"  [recovery] Retry not allowed: {reason}")
            result["final_status"] = "partial" if failure_events else "completed"
            record_retry_attempt(
                task_id, loop_id, retry_count + 1,
                recovery_plan, failure_events,
                result={"status": "exhausted", "reason": reason},
                session_id=session_id,
            )
            return result

        # ── Step 4: Create RecoveryTask ──
        result["recovery_attempted"] = True

        recovery_decision = {
            "task_id": task_id,
            "loop_id": loop_id,
            "failure_events": failure_events,
            "recovery_actions": recovery_plan.get("actionable_actions", recovery_plan.get("actions", [])),
            "retry_count": retry_count,
            "recovery_plan": recovery_plan,
            "exec_result": exec_result,
        }

        original_task = {
            "task_text": state.get("task", {}).get("task_text", ""),
            "decision_context": decision_context or {},
            "model": state.get("runtime", {}).get("model", ""),
            "provider": state.get("runtime", {}).get("provider", "opencode"),
            "project_root": (retry_context or {}).get("project_root", ""),
        }

        recovery_task = create_recovery_task(
            recovery_decision, original_task, session_id
        )

        # ── Step 5: Record retry attempt start ──
        record_retry_attempt(
            task_id, loop_id, retry_count + 1,
            recovery_plan, failure_events,
            result={"status": "started"},
            session_id=session_id,
        )

        # ── Step 6: Execute recovery via runtime provider ──
        if runtime_executor is None:
            print(f"  [recovery] No runtime executor provided. Skipping recovery execution.")
            result["recovery_success"] = False
            result["final_status"] = "partial"
            return result

        print(f"\n  [recovery] Phase 11: Executing recovery task...")
        execution_result = execute_recovery(
            recovery_task=recovery_task,
            runtime_executor=runtime_executor,
            session_id=session_id,
        )
        result["execution_result"] = execution_result

        # ── Step 7: Verify result ──
        if execution_result.get("success"):
            result["recovery_success"] = True
            result["final_status"] = "completed"
            print(f"  [recovery] Recovery succeeded!")
        else:
            result["recovery_success"] = False
            result["final_status"] = "partial"
            print(f"  [recovery] Recovery did not fully succeed")

        print(f"  [recovery] Evidence collected: {execution_result.get('evidence_collected', False)}")
        print(f"  [recovery] Verified: {execution_result.get('verified', False)}")

    except Exception as e:
        print(f"  [recovery] Recovery loop failed (non-critical): {e}")
        traceback.print_exc()
        result["errors"].append(str(e))
        result["final_status"] = "partial"

    return result


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 recovery_integration.py detect <task_id> [loop_id]")
        print("  python3 recovery_integration.py plan <task_id> [loop_id] [retry_count]")
        sys.exit(1)

    cmd = sys.argv[1]
    task_id = sys.argv[2] if len(sys.argv) > 2 else "test"
    loop_id = sys.argv[3] if len(sys.argv) > 3 else ""

    if cmd == "detect":
        events = detect_failures(task_id, loop_id=loop_id)
        print(json.dumps(events, indent=2, ensure_ascii=False))
        print(f"\n{summarize_failures(events)}")

    elif cmd == "plan":
        retry_count = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        events = detect_failures(task_id, loop_id=loop_id)
        plan = plan_recovery(events, task_id=task_id, retry_count=retry_count)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        stages = get_recovery_stages(plan)
        print(f"\nStages to replay: {stages}")