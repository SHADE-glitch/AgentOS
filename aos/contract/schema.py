"""Contract version, enums and validation helpers."""

from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "1.0"

# ── Enums ──────────────────────────────────────────────────────────────
AOS_STATUS = frozenset({"ok", "degraded", "fallback"})
PHASE = frozenset({"preflight", "postflight"})
DIFFICULTY = frozenset({"easy", "medium", "hard"})
CONFIDENCE = frozenset({"high", "medium", "low"})
ROUTE_MODE = frozenset({"lexical", "semantic", "planner"})
ESCALATION = frozenset(
    {
        "domain_unrecognized",
        "partial_known",
        "ambiguous",
        "low_separation",
        "low_confidence",
    }
)
FINAL_STATUS = frozenset({"completed", "partial", "failed"})
MEMORY_TYPE = frozenset(
    {
        "task",
        "effectiveness",
        "pattern",
        "anti-pattern",
        "failure",
        "decision",
        "hypothesis",
    }
)
MEMORY_MODE = frozenset({"enabled", "disabled", "fallback"})
PROVIDER = frozenset({"opencode", "host_delegate", "test_provider"})

# Required request keys per phase. A request may always carry more.
REQUEST_REQUIRED: dict[str, tuple[str, ...]] = {
    "preflight": ("task",),
    "postflight": ("task_id", "loop_id"),
}


class ValidationError(ValueError):
    """Raised when a contract document fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def require(condition: bool, message: str, errors: list[str]) -> None:
    """Append *message* to *errors* unless *condition* holds."""
    if not condition:
        errors.append(message)


def is_enum(value: Any, allowed: frozenset[str]) -> bool:
    """True when *value* is ``None`` or a member of *allowed*."""
    return value is None or value in allowed


def validate_schema_version(doc: dict[str, Any], errors: list[str]) -> None:
    require(
        doc.get("schema_version") == CONTRACT_VERSION,
        f"schema_version must be {CONTRACT_VERSION!r}",
        errors,
    )


def validate_phase(doc: dict[str, Any], phase: str, errors: list[str]) -> None:
    require(doc.get("phase") == phase, f"phase must be {phase!r}", errors)
