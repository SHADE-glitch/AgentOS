"""Preflight contract: build and validate the pre-execution response.

The preflight response is what the engine returns to a host *before* the
host executes the task: task classification, routing decision, recalled
memory, and the role/skill context to inject.
"""

from __future__ import annotations

from typing import Any

from aos.contract.schema import (
    AOS_STATUS,
    CONTRACT_VERSION,
    CONFIDENCE,
    DIFFICULTY,
    ESCALATION,
    MEMORY_STATUS,
    ROUTE_MODE,
    ValidationError,
    declared_version,
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
    "classification",
    "router",
    "memory",
    "skill",
    "warnings",
    "artifacts",
)


def _classification(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "category": data.get("category", ""),
        "domains": list(data.get("domains", [])),
        "roles": list(data.get("roles", [])),
        "keywords": list(data.get("keywords", [])),
        "difficulty": data.get("difficulty", "medium"),
    }


def _router(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "intent": data.get("intent", ""),
        "taxonomy": data.get("taxonomy", "abstract"),
        "lead_skill": data.get("lead_skill", ""),
        "lead_role": data.get("lead_role"),
        "support_skills": list(data.get("support_skills", [])),
        "support_roles": list(data.get("support_roles", [])),
        "confidence": data.get("confidence", "low"),
        "confidence_numeric": float(data.get("confidence_numeric", 0.0)),
        "route_mode": data.get("route_mode", "lexical"),
        "escalation_reason": data.get("escalation_reason"),
        "fallback_reason": data.get("fallback_reason"),
        "artifact": dict(data.get("artifact", {})),
    }


def _injection(data: dict[str, Any] | None) -> dict[str, Any]:
    """The block a host puts in front of the model, plus its provenance.

    ``structured`` is the same content before it was flattened, so a host
    consumes fields rather than parsing the text back apart.
    """
    data = data or {}
    return {
        "text": str(data.get("text", "")),
        "structured": list(data.get("structured", [])),
        "char_count": int(data.get("char_count", 0)),
        "truncated": bool(data.get("truncated", False)),
        "memory_ids": [str(mid) for mid in data.get("memory_ids", [])],
        "dropped": [str(mid) for mid in data.get("dropped", [])],
    }


def _memory(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    memories = list(data.get("memories", []))
    hypotheses = list(data.get("hypotheses", []))
    return {
        "retrieved": int(data.get("retrieved", len(memories) + len(hypotheses))),
        "memories": memories,
        "hypotheses": hypotheses,
        "ranking": list(data.get("ranking", [])),
        "status": data.get("status", "ok"),
        "injection": _injection(data.get("injection")),
    }


def _skill(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "lead_skill": data.get("lead_skill", ""),
        "support_skills": list(data.get("support_skills", [])),
    }


def build_preflight(
    *,
    task_id: str,
    loop_id: str,
    session_id: str = "",
    aos_status: str = "ok",
    classification: dict[str, Any] | None = None,
    router: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
    skill: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    artifacts: dict[str, Any] | None = None,
    schema_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    """Assemble a normalised preflight response document."""
    return {
        "schema_version": declared_version(schema_version),
        "phase": "preflight",
        "aos_status": aos_status,
        "task_id": task_id,
        "loop_id": loop_id,
        "session_id": session_id,
        "classification": _classification(classification),
        "router": _router(router),
        "memory": _memory(memory),
        "skill": _skill(skill),
        "warnings": list(warnings or []),
        "artifacts": dict(artifacts or {}),
    }


def fallback_preflight(
    reason: str,
    *,
    task_id: str = "",
    loop_id: str = "",
    session_id: str = "",
    schema_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    """Fail-open response: the host should proceed without AOS context."""
    return build_preflight(
        task_id=task_id,
        loop_id=loop_id,
        session_id=session_id,
        aos_status="fallback",
        memory={"status": "fallback"},
        warnings=[reason],
        schema_version=schema_version,
    )


def validate_preflight(doc: dict[str, Any]) -> None:
    """Validate a preflight document, raising :class:`ValidationError`."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        raise ValidationError(["preflight document must be a dict"])

    for key in _TOP_LEVEL:
        require(key in doc, f"missing top-level key: {key}", errors)

    validate_schema_version(doc, errors)
    validate_phase(doc, "preflight", errors)

    require(doc.get("aos_status") in AOS_STATUS, "aos_status is not a known status", errors)
    for key in ("task_id", "loop_id", "session_id"):
        require(isinstance(doc.get(key), str), f"{key} must be a string", errors)

    classification = doc.get("classification")
    require(isinstance(classification, dict), "classification must be an object", errors)
    if isinstance(classification, dict):
        require(is_enum(classification.get("difficulty"), DIFFICULTY), "classification.difficulty is invalid", errors)
        for key in ("domains", "roles", "keywords"):
            require(isinstance(classification.get(key), list), f"classification.{key} must be a list", errors)

    router = doc.get("router")
    require(isinstance(router, dict), "router must be an object", errors)
    if isinstance(router, dict):
        require(is_enum(router.get("confidence"), CONFIDENCE), "router.confidence is invalid", errors)
        require(is_enum(router.get("route_mode"), ROUTE_MODE), "router.route_mode is invalid", errors)
        require(is_enum(router.get("escalation_reason"), ESCALATION), "router.escalation_reason is invalid", errors)
        require(isinstance(router.get("confidence_numeric"), (int, float)), "router.confidence_numeric must be numeric", errors)
        for key in ("support_skills", "support_roles"):
            require(isinstance(router.get(key), list), f"router.{key} must be a list", errors)
        require("lead_skill" in router, "router.lead_skill is required", errors)

    memory = doc.get("memory")
    require(isinstance(memory, dict), "memory must be an object", errors)
    if isinstance(memory, dict):
        require(isinstance(memory.get("retrieved"), int), "memory.retrieved must be an int", errors)
        for key in ("memories", "hypotheses", "ranking"):
            require(isinstance(memory.get(key), list), f"memory.{key} must be a list", errors)
        require(is_enum(memory.get("status"), MEMORY_STATUS), "memory.status is not a known status", errors)
        injection = memory.get("injection")
        require(isinstance(injection, dict), "memory.injection must be an object", errors)
        if isinstance(injection, dict):
            require(isinstance(injection.get("text"), str), "memory.injection.text must be a string", errors)
            require(
                isinstance(injection.get("structured"), list),
                "memory.injection.structured must be a list",
                errors,
            )
            require(
                isinstance(injection.get("char_count"), int),
                "memory.injection.char_count must be an int",
                errors,
            )
            require(
                isinstance(injection.get("truncated"), bool),
                "memory.injection.truncated must be a bool",
                errors,
            )
            for key in ("memory_ids", "dropped"):
                require(isinstance(injection.get(key), list), f"memory.injection.{key} must be a list", errors)

    require(isinstance(doc.get("skill"), dict), "skill must be an object", errors)

    require(isinstance(doc.get("warnings"), list), "warnings must be a list", errors)
    require(isinstance(doc.get("artifacts"), dict), "artifacts must be an object", errors)

    if errors:
        raise ValidationError(errors)
