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
    assert CONTRACT_VERSION == "1.0"


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
