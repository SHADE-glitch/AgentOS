"""Contract version, enums and validation helpers."""

from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "1.1"

# A request may declare any supported version and the document it gets back is
# written in that same version. 1.1 only adds fields, so a host that still pins
# "1.0" keeps passing its own version check instead of failing at the exact
# moment the engine degraded and it needed to carry on.
SUPPORTED_VERSIONS = ("1.0", "1.1")

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
# Health of the recall step itself, reported next to whatever it returned, so a
# host can tell "nothing was relevant" from "retrieval did not run".
MEMORY_STATUS = frozenset({"ok", "degraded", "skipped", "fallback"})
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


def declared_version(value: Any) -> str:
    """The version to write a document in: the caller's, when we support it."""
    return value if value in SUPPORTED_VERSIONS else CONTRACT_VERSION


def validate_schema_version(doc: dict[str, Any], errors: list[str]) -> None:
    require(
        doc.get("schema_version") in SUPPORTED_VERSIONS,
        f"schema_version must be one of {', '.join(repr(v) for v in SUPPORTED_VERSIONS)}",
        errors,
    )


def validate_phase(doc: dict[str, Any], phase: str, errors: list[str]) -> None:
    require(doc.get("phase") == phase, f"phase must be {phase!r}", errors)
