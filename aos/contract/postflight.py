"""Postflight contract: build and validate the post-execution response.

The postflight response is what the engine returns to a host *after* the
task has been executed: final status, collected evidence, recovery
outcome, and what the learning pipeline did with the result.
"""

from __future__ import annotations

from typing import Any

from aos.contract.schema import (
    AOS_STATUS,
    CONTRACT_VERSION,
    FINAL_STATUS,
    ValidationError,
    is_enum,
    require,
    validate_phase,
    validate_schema_version,
)

_TOP_LEVEL = (
    "schema_version",
    "phase",
    "aos_status",
    "task_id",
    "loop_id",
    "session_id",
    "final_status",
    "evidence_path",
    "evidence",
    "recovery",
    "learning",
    "replayed",
)


def _evidence(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "path": data.get("path", ""),
        "repo_resolved": bool(data.get("repo_resolved", False)),
        "files_changed": list(data.get("files_changed", [])),
        "test_passed": data.get("test_passed"),
    }


def _recovery(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "failures_detected": int(data.get("failures_detected", 0)),
        "recovery_attempted": bool(data.get("recovery_attempted", False)),
        "recovery_success": bool(data.get("recovery_success", False)),
        "final_status": data.get("final_status", "completed"),
        "plan": data.get("plan"),
    }


def _learning(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "candidates_recorded": int(data.get("candidates_recorded", 0)),
        "hypotheses_pending_review": int(data.get("hypotheses_pending_review", 0)),
        "promoted": int(data.get("promoted", 0)),
    }


def build_postflight(
    *,
    task_id: str,
    loop_id: str,
    session_id: str = "",
    aos_status: str = "ok",
    final_status: str = "completed",
    evidence_path: str = "",
    evidence: dict[str, Any] | None = None,
    recovery: dict[str, Any] | None = None,
    learning: dict[str, Any] | None = None,
    replayed: bool = False,
) -> dict[str, Any]:
    """Assemble a normalised postflight response document."""
    return {
        "schema_version": CONTRACT_VERSION,
        "phase": "postflight",
        "aos_status": aos_status,
        "task_id": task_id,
        "loop_id": loop_id,
        "session_id": session_id,
        "final_status": final_status,
        "evidence_path": evidence_path,
        "evidence": _evidence(evidence),
        "recovery": _recovery(recovery),
        "learning": _learning(learning),
        "replayed": bool(replayed),
    }


def fallback_postflight(reason: str, *, task_id: str = "", loop_id: str = "", session_id: str = "") -> dict[str, Any]:
    """Fail-open response: the host should proceed without AOS finalisation."""
    return build_postflight(
        task_id=task_id,
        loop_id=loop_id,
        session_id=session_id,
        aos_status="fallback",
        final_status="completed",
        learning={"candidates_recorded": 0, "hypotheses_pending_review": 0, "promoted": 0},
    )


def validate_postflight(doc: dict[str, Any]) -> None:
    """Validate a postflight document, raising :class:`ValidationError`."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        raise ValidationError(["postflight document must be a dict"])

    for key in _TOP_LEVEL:
        require(key in doc, f"missing top-level key: {key}", errors)

    validate_schema_version(doc, errors)
    validate_phase(doc, "postflight", errors)

    require(doc.get("aos_status") in AOS_STATUS, "aos_status is not a known status", errors)
    require(doc.get("final_status") in FINAL_STATUS, "final_status is not a known status", errors)
    for key in ("task_id", "loop_id", "session_id", "evidence_path"):
        require(isinstance(doc.get(key), str), f"{key} must be a string", errors)

    evidence = doc.get("evidence")
    require(isinstance(evidence, dict), "evidence must be an object", errors)
    if isinstance(evidence, dict):
        require(isinstance(evidence.get("files_changed"), list), "evidence.files_changed must be a list", errors)

    recovery = doc.get("recovery")
    require(isinstance(recovery, dict), "recovery must be an object", errors)
    if isinstance(recovery, dict):
        require(isinstance(recovery.get("failures_detected"), int), "recovery.failures_detected must be an int", errors)
        require(is_enum(recovery.get("final_status"), FINAL_STATUS), "recovery.final_status is invalid", errors)

    learning = doc.get("learning")
    require(isinstance(learning, dict), "learning must be an object", errors)
    if isinstance(learning, dict):
        for key in ("candidates_recorded", "hypotheses_pending_review", "promoted"):
            require(isinstance(learning.get(key), int), f"learning.{key} must be an int", errors)

    require(isinstance(doc.get("replayed"), bool), "replayed must be a bool", errors)

    if errors:
        raise ValidationError(errors)
