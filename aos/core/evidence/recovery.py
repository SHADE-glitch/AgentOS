"""Failure detection and recovery planning.

Ported from ``recovery/failure_detector.py`` and ``recovery/recovery_planner.py``.
The invariant is preserved and is the point of this module: recovery only
*plans*. Every strategy has ``auto_modify_code: False``; nothing here retries,
edits files, or re-runs anything. A caller that wants to act on a plan must do
so explicitly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

RECOVERY_STRATEGIES: dict[str, dict[str, Any]] = {
    "failed_tests": {
        "action": "inspect_and_retry",
        "description": "Inspect test failure output, update the plan, retry",
        "target_stages": ["execute", "evidence"],
        "max_retries": 2,
        "auto_modify_code": False,
    },
    "missing_evidence": {
        "action": "collect_evidence",
        "description": "Collect the missing evidence artifact",
        "target_stages": ["evidence"],
        "max_retries": 1,
        "auto_modify_code": False,
    },
    "memory_claim_invalid": {
        "action": "retrieve_memory_again",
        "description": "Re-retrieve memory and mark unsupported claims",
        "target_stages": ["recall"],
        "max_retries": 1,
        "auto_modify_code": False,
    },
    "runtime_error": {
        "action": "retry_execution",
        "description": "Retry execution with adjusted context",
        "target_stages": ["execute"],
        "max_retries": 2,
        "auto_modify_code": False,
    },
    "failed_validation": {
        "action": "resolve_validation_issues",
        "description": "Resolve the reported validation issues",
        "target_stages": ["evidence"],
        "max_retries": 1,
        "auto_modify_code": False,
    },
    "incomplete_result": {
        "action": "regenerate_result",
        "description": "Regenerate an incomplete result",
        "target_stages": ["finalize"],
        "max_retries": 1,
        "auto_modify_code": False,
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_failures(
    *,
    task_id: str = "",
    loop_id: str = "",
    execution: Optional[dict[str, Any]] = None,
    evidence: Optional[dict[str, Any]] = None,
    validation: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Return failure events, most severe first.

    Sources: the provider result (``execution``), the evidence bundle, and an
    optional validation result.
    """
    events: list[dict[str, Any]] = []
    now = _now_iso()

    def event(failure_type: str, source: str, severity: str, action: str, detail: dict[str, Any]) -> None:
        events.append(
            {
                "type": failure_type,
                "source": source,
                "severity": severity,
                "recommended_action": action,
                "evidence": detail,
                "detected_at": now,
                "task_id": task_id,
                "loop_id": loop_id,
            }
        )

    if execution:
        status = execution.get("status", "")
        if status in ("error", "failed"):
            event(
                "runtime_error",
                "provider",
                "critical",
                "retry_execution",
                {"status": status, "error": execution.get("error", "")},
            )
        elif status == "timeout":
            event(
                "runtime_error",
                "provider",
                "critical",
                "retry_execution",
                {"status": status, "error": execution.get("error", "")},
            )

    if evidence is None:
        event("missing_evidence", "evidence_collector", "high", "collect_evidence", {})
    else:
        after = evidence.get("after", {})
        exit_code = after.get("test_exit_code")
        if exit_code is not None and exit_code != 0:
            event(
                "failed_tests",
                "evidence_collector",
                "critical",
                "inspect_and_retry",
                {
                    "test_command": after.get("test_command", ""),
                    "test_exit_code": exit_code,
                    "test_stdout": (after.get("test_stdout") or "")[:500],
                },
            )

    if validation and not validation.get("valid", True):
        event(
            "failed_validation",
            "validator",
            "high",
            "resolve_validation_issues",
            {"issues": validation.get("issues", [])},
        )

    events.sort(key=lambda e: SEVERITY_ORDER.get(e.get("severity", "low"), 99))
    return events


def has_critical_failures(events: list[dict[str, Any]]) -> bool:
    return any(e.get("severity") == "critical" for e in events)


def plan_recovery(
    failure_events: list[dict[str, Any]], *, task_id: str = "", loop_id: str = "", retry_count: int = 0
) -> dict[str, Any]:
    """Turn failure events into a read-only recovery plan."""
    if not failure_events:
        return {
            "recovery_needed": False,
            "task_id": task_id,
            "loop_id": loop_id,
            "generated_at": _now_iso(),
            "actions": [],
            "target_stages": [],
            "retry_exhausted": False,
            "summary": "No failures detected; recovery not needed.",
        }

    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    target_stages: set[str] = set()
    retry_exhausted = False

    for event in failure_events:
        failure_type = event.get("type", "")
        strategy = RECOVERY_STRATEGIES.get(failure_type)
        if strategy is None:
            strategy = {
                "action": "retry_execution",
                "description": f"Unknown failure type {failure_type!r}; retry execution",
                "target_stages": ["execute"],
                "max_retries": 1,
                "auto_modify_code": False,
            }

        if retry_count >= strategy["max_retries"]:
            retry_exhausted = True
            actions.append(
                {
                    "action": "retry_exhausted",
                    "description": f"retry budget exhausted for {failure_type!r}",
                    "target_stages": [],
                    "max_retries": 0,
                    "auto_modify_code": False,
                    "source_failure": failure_type,
                }
            )
            continue

        if strategy["action"] in seen:
            continue
        seen.add(strategy["action"])
        target_stages.update(strategy["target_stages"])
        actions.append(
            {
                "action": strategy["action"],
                "description": strategy["description"],
                "target_stages": list(strategy["target_stages"]),
                "max_retries": strategy["max_retries"],
                "auto_modify_code": strategy["auto_modify_code"],
                "source_failure": failure_type,
            }
        )

    return {
        "recovery_needed": True,
        "task_id": task_id,
        "loop_id": loop_id,
        "generated_at": _now_iso(),
        "actions": actions,
        "target_stages": sorted(target_stages),
        "retry_exhausted": retry_exhausted,
        "summary": (
            f"{len(failure_events)} failure(s), {len(actions)} planned action(s); "
            "planning only — no automatic code changes"
        ),
    }
