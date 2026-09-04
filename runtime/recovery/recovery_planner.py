#!/usr/bin/env python3
"""
Recovery Planner — Phase 10: Autonomous Recovery Loop

Translates FailureEvents into actionable RecoveryPlans.

Rules:
  - NEVER auto-modify business code
  - NEVER auto-promote memory candidates
  - NEVER fake success
  - All recovery actions must produce evidence

Recovery strategies per failure type:
  - failed_tests          → inspect failure output, update plan, retry
  - missing_evidence      → collect missing artifact, regenerate report
  - memory_claim_invalid  → retrieve memory again, mark unsupported
  - runtime_error         → retry with adjusted context
  - failed_validation     → resolve specific validation issues
  - incomplete_teamresult → regenerate team result

Each plan has:
  - action: what to do
  - target_stage: which stage(s) to re-run
  - retry_budget: max retries (default 2)
  - evidence_required: what evidence must be produced
"""

import os
from datetime import datetime, timezone

BASE = "/home/shade/.agents"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Recovery strategy mapping ────────────────────────────────────

RECOVERY_STRATEGIES = {
    "failed_tests": {
        "action": "inspect_and_retry",
        "description": "Inspect test failure output, update execution plan, retry",
        "target_stages": ["runtime", "code_validation"],
        "max_retries": 2,
        "evidence_required": ["test_command", "test_exit_code", "test_stdout"],
        "auto_modify_code": False,
    },
    "missing_evidence": {
        "action": "collect_evidence",
        "description": "Collect missing evidence artifacts, regenerate report",
        "target_stages": ["evidence"],
        "max_retries": 1,
        "evidence_required": ["evidence_file"],
        "auto_modify_code": False,
    },
    "memory_claim_invalid": {
        "action": "retrieve_memory_again",
        "description": "Re-retrieve memory, mark unsupported claims",
        "target_stages": ["retrieval"],
        "max_retries": 1,
        "evidence_required": ["retrieval_artifact"],
        "auto_modify_code": False,
    },
    "runtime_error": {
        "action": "retry_execution",
        "description": "Retry runtime execution with adjusted context",
        "target_stages": ["runtime"],
        "max_retries": 2,
        "evidence_required": ["test_command", "test_exit_code"],
        "auto_modify_code": False,
    },
    "failed_validation": {
        "action": "resolve_validation_issues",
        "description": "Resolve specific TeamResult validation issues",
        "target_stages": ["collaboration", "runtime"],
        "max_retries": 1,
        "evidence_required": ["evidence_file", "team_result"],
        "auto_modify_code": False,
    },
    "incomplete_teamresult": {
        "action": "regenerate_team_result",
        "description": "Regenerate incomplete TeamResult",
        "target_stages": ["collaboration"],
        "max_retries": 1,
        "evidence_required": ["team_result"],
        "auto_modify_code": False,
    },
}


def plan_recovery(failure_events, task_id="", loop_id="", retry_count=0):
    """
    Generate a recovery plan from failure events.

    Args:
        failure_events: list of RecoveryEvent dicts from failure_detector.detect_failures()
        task_id: str
        loop_id: str
        retry_count: int — current retry attempt number (0-indexed)

    Returns:
        dict — RecoveryPlan with actions, target stages, and metadata
    """
    if not failure_events:
        return {
            "recovery_needed": False,
            "task_id": task_id,
            "loop_id": loop_id,
            "generated_at": _now_iso(),
            "actions": [],
            "target_stages": [],
            "summary": "No failures detected. Recovery not needed.",
        }

    actions = []
    seen_actions = set()
    all_target_stages = set()

    for event in failure_events:
        failure_type = event.get("type", "")
        strategy = RECOVERY_STRATEGIES.get(failure_type)

        if not strategy:
            # Unknown failure type — generic retry
            actions.append({
                "action": "retry_execution",
                "description": f"Unknown failure type '{failure_type}', retry execution",
                "target_stages": ["runtime"],
                "max_retries": 1,
                "evidence_required": [],
                "source_event": event,
            })
            all_target_stages.add("runtime")
            continue

        # Check retry budget
        if retry_count >= strategy["max_retries"]:
            actions.append({
                "action": "retry_exhausted",
                "description": f"Retry budget exhausted for '{failure_type}' (max {strategy['max_retries']})",
                "target_stages": [],
                "max_retries": 0,
                "evidence_required": [],
                "source_event": event,
            })
            continue

        # Deduplicate actions
        action_key = strategy["action"]
        if action_key not in seen_actions:
            seen_actions.add(action_key)
            actions.append({
                "action": strategy["action"],
                "description": strategy["description"],
                "target_stages": strategy["target_stages"],
                "max_retries": strategy["max_retries"],
                "evidence_required": strategy["evidence_required"],
                "auto_modify_code": strategy["auto_modify_code"],
                "source_event": event,
            })
            for stage in strategy["target_stages"]:
                all_target_stages.add(stage)

    # Determine retry count for this plan
    plan_retry_count = retry_count + 1
    retry_exhausted = any(a["action"] == "retry_exhausted" for a in actions)
    actionable = [a for a in actions if a["action"] != "retry_exhausted"]

    can_recover = len(actionable) > 0
    stages_to_replay = sorted(all_target_stages)

    return {
        "recovery_needed": True,
        "can_recover": can_recover,
        "retry_exhausted": retry_exhausted,
        "task_id": task_id,
        "loop_id": loop_id,
        "generated_at": _now_iso(),
        "retry_count": plan_retry_count,
        "actions": actions,
        "actionable_actions": actionable,
        "target_stages": stages_to_replay,
        "summary": _summarize_plan(actions, can_recover, retry_exhausted),
    }


def _summarize_plan(actions, can_recover, retry_exhausted):
    """Generate a human-readable summary."""
    if not actions:
        return "No actions needed."
    lines = []
    for a in actions:
        lines.append(f"  - {a['action']}: {a['description']}")
    if retry_exhausted:
        lines.append("  (retry budget exhausted for some failures)")
    if not can_recover:
        lines.append("  (no recoverable actions — manual intervention required)")
    return "\n".join(lines)


def get_recovery_stages(plan):
    """
    Return the list of stages that need to be replayed, in pipeline order.

    Pipeline order: retrieval → router → skill → orchestrator → collaboration → runtime → code_validation → collector → validator → promoter → reconciler
    """
    PIPELINE_ORDER = [
        "retrieval", "router", "skill", "orchestrator",
        "collaboration", "runtime", "code_validation",
        "collector", "validator", "promoter", "reconciler",
        "evidence",
    ]
    target = set(plan.get("target_stages", []))
    # Find the earliest stage that needs replay
    earliest_idx = None
    for stage in target:
        if stage in PIPELINE_ORDER:
            idx = PIPELINE_ORDER.index(stage)
            if earliest_idx is None or idx < earliest_idx:
                earliest_idx = idx

    if earliest_idx is None:
        return []

    # Replay from earliest stage to end of pipeline (up to reconciler)
    return PIPELINE_ORDER[earliest_idx:]


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python3 recovery_planner.py <failure_events_json> [task_id] [retry_count]")
        print("Example: python3 recovery_planner.py '[{\"type\":\"failed_tests\",\"severity\":\"critical\"}]' RT-001 0")
        sys.exit(1)

    events = json.loads(sys.argv[1])
    task_id = sys.argv[2] if len(sys.argv) > 2 else ""
    retry_count = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    plan = plan_recovery(events, task_id=task_id, retry_count=retry_count)
    print(json.dumps(plan, indent=2, ensure_ascii=False))