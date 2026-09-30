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
# What the host says happened. Distinct from FINAL_STATUS, which is what the
# engine concluded after checking it — the two may differ.
OUTCOME = frozenset({"success", "failure", "partial"})

# Required request keys per phase. A request may always carry more.
REQUEST_REQUIRED: dict[str, tuple[str, ...]] = {
    "preflight": ("task",),
    "postflight": ("task_id", "loop_id"),
}

# Every inbound field the engine reads, per phase. Anything outside this set is
# reported as ignored instead of being dropped in silence — silently discarded
# keys are exactly how the outcome channel went missing in the first place.
REQUEST_FIELDS: dict[str, frozenset[str]] = {
    "preflight": frozenset(
        {
            "schema_version",
            "phase",
            "task",
            "task_id",
            "session_id",
            "cwd",
            "memory_mode",
            "provider",
            "model",
        }
    ),
    "postflight": frozenset(
        {
            "schema_version",
            "phase",
            "task_id",
            "loop_id",
            "session_id",
            "cwd",
            "memory_mode",
            "provider",
            "model",
            "outcome",
            "quality_score",
            "test_command",
            "test_stdout",
            "test_stderr",
            "test_exit_code",
            "compile_command",
            "expected_files",
            "validate",
        }
    ),
}

_STR_FIELDS = ("task", "task_id", "loop_id", "session_id", "cwd", "model",
               "test_command", "test_stdout", "test_stderr", "compile_command")
_NUM_FIELDS = ("quality_score", "test_exit_code")
_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "memory_mode": MEMORY_MODE,
    "provider": PROVIDER,
    "outcome": OUTCOME,
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


def _type_name(expected: tuple[type, ...]) -> str:
    return " or ".join(t.__name__ for t in expected)


def validate_request(payload: dict[str, Any], *, phase: str) -> list[str]:
    """Check an inbound host payload and return the problems, never raising.

    A malformed request is answered with a fallback document rather than an
    exception, because the host must always receive something it can parse.
    Absent fields are the caller's default, not an error — except the required
    ones named in :data:`REQUEST_REQUIRED`.
    """
    errors: list[str] = []
    allowed = REQUEST_FIELDS.get(phase)
    if allowed is None:
        return [f"unknown phase: {phase!r}"]

    declared = payload.get("schema_version")
    require(
        declared is None or declared in SUPPORTED_VERSIONS,
        f"schema_version must be one of {', '.join(repr(v) for v in SUPPORTED_VERSIONS)}",
        errors,
    )
    require(payload.get("phase", phase) == phase, f"phase must be {phase!r}", errors)

    for key in REQUEST_REQUIRED[phase]:
        value = payload.get(key)
        require(
            isinstance(value, str) and bool(value.strip()),
            f"{key} is required and must be a non-empty string",
            errors,
        )

    for key, members in _ENUM_FIELDS.items():
        if payload.get(key) is not None:
            require(payload[key] in members, f"{key} is not a known value", errors)

    for key in _STR_FIELDS:
        if key in payload and key not in REQUEST_REQUIRED[phase]:
            require(isinstance(payload[key], str), f"{key} must be a string", errors)

    for key in _NUM_FIELDS:
        value = payload.get(key)
        if value is None:
            continue
        # bool is a subclass of int; a "true" quality score is a caller bug.
        require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{key} must be a number",
            errors,
        )

    files = payload.get("expected_files")
    if files is not None:
        require(
            isinstance(files, list) and all(isinstance(entry, str) for entry in files),
            "expected_files must be a list of strings",
            errors,
        )
    if "validate" in payload:
        require(isinstance(payload["validate"], bool), "validate must be a boolean", errors)

    return errors


def unread_request_fields(payload: dict[str, Any], *, phase: str) -> list[str]:
    """Request keys the engine does not read, so the caller can be told."""
    allowed = REQUEST_FIELDS.get(phase, frozenset())
    return sorted(str(key) for key in payload if key not in allowed)
