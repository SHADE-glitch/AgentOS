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
    SIGNAL_FIELDS,
    ValidationError,
    declared_version,
    is_enum,
    require,
    validate_phase,
    validate_schema_version,
)

# Verdicts are not signals: a host that sends ``outcome`` has already judged the
# run, and :func:`aos.core.outcome.synthesize` believes it instead of averaging.
# They ride in the same object because a host that accumulates evidence naturally
# accumulates its conclusion beside it.
VERDICT_FIELDS = frozenset({"outcome", "quality_score"})

# What a plugin may send, as one named set the plugin and the engine can be
# checked against each other instead of two lists kept in sync by hand.
PLUGIN_POSTFLIGHT_REQUEST_FIELDS = SIGNAL_FIELDS | VERDICT_FIELDS | frozenset({"skill_used"})


def collect_signals(payload: dict[str, Any]) -> dict[str, Any]:
    """Gather everything the host reported about a finished run into one object.

    Two shapes are accepted: a nested ``signals`` object — what a plugin with an
    accumulator sends — and the flat top-level keys, which are what this contract
    has always read. The nested object wins for any key it carries, because it is
    the deliberate statement rather than a convenience.
    """
    nested = payload.get("signals")
    nested = nested if isinstance(nested, dict) else {}
    known = SIGNAL_FIELDS | VERDICT_FIELDS | frozenset({"skill_used"})
    signals: dict[str, Any] = {}
    for key in sorted(known):
        if key in nested:
            signals[key] = nested[key]
        elif key in payload:
            signals[key] = payload[key]
    return signals


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
    "aos_error",
    "warnings",
)


def _evidence(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "path": data.get("path", ""),
        "repo_resolved": bool(data.get("repo_resolved", False)),
        "files_changed": list(data.get("files_changed", [])),
        # Files that were already modified when preflight took its snapshot. A
        # reviewer comparing `files_changed` against the diff needs to know which
        # of them this run is actually responsible for.
        "preexisting_files": list(data.get("preexisting_files", [])),
        # "preflight" when the baseline is the one taken before the run,
        # "recaptured at postflight" when there was none — a reviewer needs to
        # know whether `files_changed` is a real diff or a best effort.
        "before_source": data.get("before_source", ""),
        "test_passed": data.get("test_passed"),
    }


def _recovery(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "failures_detected": int(data.get("failures_detected", 0)),
        "recovery_attempted": bool(data.get("recovery_attempted", False)),
        "recovery_success": bool(data.get("recovery_success", False)),
        # No verdict, rather than an invented "completed": a fail-open document
        # whose recovery block contradicts the top-level failure is the same
        # class of lie as reporting an unlabeled run as a success.
        "final_status": data.get("final_status"),
        "plan": data.get("plan"),
    }


def _learning(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "candidates_recorded": int(data.get("candidates_recorded", 0)),
        "hypotheses_pending_review": int(data.get("hypotheses_pending_review", 0)),
        "promoted": int(data.get("promoted", 0)),
        # The engine is telling the host "I could not decide, and a human has to".
        # Without it the host cannot tell a labelled run from an assumed one.
        "needs_review": bool(data.get("needs_review", False)),
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
    aos_error: str = "",
    warnings: list[str] | None = None,
    schema_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    """Assemble a normalised postflight response document."""
    return {
        "schema_version": declared_version(schema_version),
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
        "aos_error": aos_error,
        "warnings": list(warnings or []),
    }


def fallback_postflight(
    reason: str,
    *,
    task_id: str = "",
    loop_id: str = "",
    session_id: str = "",
    schema_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    """Fail-open response: the host should proceed without AOS finalisation.

    ``final_status`` is ``failed``, not ``completed``: a loop the engine could
    not finish did not complete, and reporting otherwise is what let an
    unlabeled run look like a successful one. The reason travels in
    ``aos_error`` instead of being dropped.
    """
    return build_postflight(
        task_id=task_id,
        loop_id=loop_id,
        session_id=session_id,
        aos_status="fallback",
        final_status="failed",
        evidence_path="",
        learning={"candidates_recorded": 0, "hypotheses_pending_review": 0, "promoted": 0},
        aos_error=reason,
        schema_version=schema_version,
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
    require(isinstance(doc.get("aos_error"), str), "aos_error must be a string", errors)
    require(isinstance(doc.get("warnings"), list), "warnings must be a list", errors)

    if errors:
        raise ValidationError(errors)
