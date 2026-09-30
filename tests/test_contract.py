"""Contract tests.

The most important assertion here is that the frozen contract still carries
every field the host plugin actually reads (``hosts/opencode/plugin/index.js``).
If a field is dropped, this test fails before a host can break.
"""

from __future__ import annotations

import pytest

from aos.contract import (
    CONTRACT_VERSION,
    ValidationError,
    build_postflight,
    build_preflight,
    to_adapter_context,
    validate_postflight,
    validate_preflight,
)
from aos.contract.postflight import fallback_postflight
from aos.contract.preflight import fallback_preflight
from aos.contract.schema import SUPPORTED_VERSIONS

# Fields the OpenCode plugin reads from a preflight response, as dotted paths.
PLUGIN_PREFLIGHT_FIELDS = (
    "task_id",
    "loop_id",
    "session_id",
    "aos_status",
    "classification.category",
    "classification.difficulty",
    "classification.roles",
    "router.intent",
    "router.lead_skill",
    "router.support_skills",
    "router.confidence",
    "memory.retrieved",
    "memory.memories",
    "memory.injection.text",
    "skill.skills_loaded",
    "warnings",
)

# Fields the OpenCode plugin reads from a postflight response.
PLUGIN_POSTFLIGHT_FIELDS = (
    "task_id",
    "loop_id",
    "session_id",
    "final_status",
    "evidence_path",
    "recovery.failures_detected",
)

# The 1.0 top-level field set, restated here as a literal rather than imported,
# so deleting or retyping one of these keys fails this test instead of silently
# breaking a host that pins the contract version.
FROZEN_1_0_PREFLIGHT = frozenset(
    {
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
    }
)
FROZEN_1_0_POSTFLIGHT = frozenset(
    {
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
    }
)

# What 1.1 adds on top. Nothing may be removed, so this is a growth list only.
EXTRA_1_1_PREFLIGHT: frozenset[str] = frozenset()
EXTRA_1_1_POSTFLIGHT = frozenset({"aos_error", "warnings"})


def _has_path(doc: dict, dotted: str) -> bool:
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def _sample_preflight() -> dict:
    return build_preflight(
        task_id="HOST-ABC123",
        loop_id="LOOP-20260930120000-ABCD",
        session_id="SESS-1",
        classification={"category": "backend", "domains": ["backend"], "roles": ["backend-architect"], "difficulty": "hard"},
        router={"intent": "bugfix", "lead_skill": "bugfix", "lead_role": "code-reviewer", "support_skills": ["test"], "confidence": "high", "confidence_numeric": 0.82},
        memory={"retrieved": 1, "memories": [{"memory_id": "E-002", "content": "x"}]},
        skill={"lead_skill": "code-reviewer", "skills_loaded": ["code-reviewer"]},
        warnings=["low evidence"],
    )


def _sample_postflight() -> dict:
    return build_postflight(
        task_id="HOST-ABC123",
        loop_id="LOOP-20260930120000-ABCD",
        session_id="SESS-1",
        final_status="completed",
        evidence_path="store/evidence/SESS-1/evidence-HOST-ABC123.json",
        recovery={"failures_detected": 0},
        learning={"candidates_recorded": 2, "hypotheses_pending_review": 1, "promoted": 0},
    )


def test_contract_version():
    assert CONTRACT_VERSION == "1.1"
    # A host pinned to the previous version must still be served.
    assert SUPPORTED_VERSIONS == ("1.0", "1.1")


def test_preflight_field_set_is_frozen_plus_declared_additions():
    doc = _sample_preflight()
    assert FROZEN_1_0_PREFLIGHT <= set(doc)
    assert set(doc) == FROZEN_1_0_PREFLIGHT | EXTRA_1_1_PREFLIGHT


def test_postflight_field_set_is_frozen_plus_declared_additions():
    doc = _sample_postflight()
    assert FROZEN_1_0_POSTFLIGHT <= set(doc)
    assert set(doc) == FROZEN_1_0_POSTFLIGHT | EXTRA_1_1_POSTFLIGHT


# ── version negotiation ────────────────────────────────────────────────
def test_1_0_request_is_served_1_0():
    doc = build_preflight(task_id="T", loop_id="L", schema_version="1.0")
    assert doc["schema_version"] == "1.0"
    validate_preflight(doc)
    assert "injection" in doc["memory"]  # additive keys arrive regardless


def test_1_1_request_gets_injection():
    doc = build_preflight(task_id="T", loop_id="L", schema_version="1.1")
    assert doc["schema_version"] == "1.1"
    assert set(doc["memory"]["injection"]) == {
        "text",
        "structured",
        "char_count",
        "truncated",
        "memory_ids",
        "dropped",
    }


def test_unsupported_version_is_answered_in_the_engines_own():
    """An unknown declaration is answered in a version we do support.

    Answering "0.9" would hand back a document no validator accepts, so the
    caller's own check fails at the moment it is trying to degrade.
    """
    assert build_preflight(task_id="T", loop_id="L", schema_version="0.9")["schema_version"] == "1.1"
    assert build_postflight(task_id="T", loop_id="L", schema_version="")["schema_version"] == "1.1"
    assert fallback_preflight("boom", schema_version="1.0")["schema_version"] == "1.0"


def test_validate_still_rejects_a_version_we_do_not_support():
    doc = _sample_preflight()
    doc["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        validate_preflight(doc)


# ── honesty of the fail-open documents ─────────────────────────────────
def test_fallback_postflight_reports_failure_not_completion():
    doc = fallback_postflight("core lifecycle not yet ported", loop_id="L")
    assert doc["final_status"] == "failed"
    assert doc["aos_status"] == "fallback"
    # The reason must travel, not be discarded on the way out.
    assert doc["aos_error"] == "core lifecycle not yet ported"
    validate_postflight(doc)


def test_fallback_postflight_does_not_claim_a_recovery_verdict():
    doc = fallback_postflight("boom", loop_id="L")
    # The recovery planner never ran, so it must not assert a completion verdict
    # that contradicts the top-level failure.
    assert doc["recovery"]["final_status"] is None
    assert doc["final_status"] == "failed"
    validate_postflight(doc)


def test_recovery_verdict_is_kept_when_the_loop_ran():
    doc = build_postflight(
        task_id="T",
        loop_id="L",
        final_status="partial",
        recovery={"failures_detected": 2, "final_status": "partial", "plan": {"steps": []}},
    )
    assert doc["recovery"]["final_status"] == "partial"
    validate_postflight(doc)


def test_fallback_preflight_marks_recall_as_not_run():
    doc = fallback_preflight("boom")
    assert doc["memory"]["status"] == "fallback"
    assert doc["memory"]["injection"]["text"] == ""
    validate_preflight(doc)


# ── injection and recall health are validated, not just present ────────
def test_validate_preflight_rejects_bad_memory_status():
    doc = _sample_preflight()
    doc["memory"]["status"] = "vibing"
    with pytest.raises(ValidationError):
        validate_preflight(doc)


def test_validate_preflight_rejects_a_non_string_injection_text():
    doc = _sample_preflight()
    doc["memory"]["injection"]["text"] = ["<agent_os>"]
    with pytest.raises(ValidationError):
        validate_preflight(doc)


def test_memory_defaults_are_valid():
    doc = build_preflight(task_id="T", loop_id="L")
    assert doc["memory"]["status"] == "ok"
    assert doc["memory"]["injection"] == {
        "text": "",
        "structured": [],
        "char_count": 0,
        "truncated": False,
        "memory_ids": [],
        "dropped": [],
    }


def test_preflight_carries_every_field_the_plugin_reads():
    doc = _sample_preflight()
    missing = [field for field in PLUGIN_PREFLIGHT_FIELDS if not _has_path(doc, field)]
    assert missing == []


def test_postflight_carries_every_field_the_plugin_reads():
    doc = _sample_postflight()
    missing = [field for field in PLUGIN_POSTFLIGHT_FIELDS if not _has_path(doc, field)]
    assert missing == []


def test_build_and_validate_preflight_roundtrip():
    validate_preflight(_sample_preflight())


def test_build_and_validate_postflight_roundtrip():
    validate_postflight(_sample_postflight())


def test_preflight_defaults_are_valid():
    doc = build_preflight(task_id="T", loop_id="L")
    validate_preflight(doc)
    assert doc["classification"]["difficulty"] == "medium"
    assert doc["router"]["confidence"] == "low"
    assert doc["router"]["route_mode"] == "lexical"


def test_validate_preflight_rejects_missing_key():
    doc = _sample_preflight()
    del doc["router"]
    with pytest.raises(ValidationError):
        validate_preflight(doc)


def test_validate_preflight_rejects_bad_enum():
    doc = _sample_preflight()
    doc["router"]["route_mode"] = "telepathy"
    with pytest.raises(ValidationError):
        validate_preflight(doc)


def test_validate_preflight_rejects_wrong_schema_version():
    doc = _sample_preflight()
    doc["schema_version"] = "0.9"
    with pytest.raises(ValidationError):
        validate_preflight(doc)


def test_validate_postflight_rejects_bad_final_status():
    doc = _sample_postflight()
    doc["final_status"] = "done"
    with pytest.raises(ValidationError):
        validate_postflight(doc)


def test_fallback_documents_validate():
    validate_preflight(fallback_preflight("boom"))
    validate_postflight(fallback_postflight("boom"))


def test_fallback_marks_status():
    assert fallback_preflight("boom")["aos_status"] == "fallback"
    assert fallback_postflight("boom")["aos_status"] == "fallback"


def test_legacy_adapter_context_shape():
    doc = _sample_preflight()
    legacy = to_adapter_context(doc)
    assert legacy["aos_status"] == "completed"
    assert legacy["decision"]["classification"]["category"] == "backend"
    assert legacy["orchestration"]["lead_agent"] == "code-reviewer"
    assert legacy["orchestration"]["support_agents"] == []
