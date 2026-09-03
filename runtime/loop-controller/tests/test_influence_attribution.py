#!/usr/bin/env python3
"""
Phase 8.2.1.5 — Decision Influence Attribution Tests

Validates that the new influence attribution correctly detects:
  A. Relevant hypothesis retrieved → injected → agent referenced → correct attribution
  B. Unrelated hypothesis → no influence
  C. Established memory → keeps original behavior
  D. F-NEG → no generic hypothesis influence

These tests are deterministic: they call _determine_influence() and
_detect_hypothesis_engagement() directly, without requiring a real
runtime provider.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from runtime_adapter import (
    _determine_influence,
    _detect_hypothesis_engagement,
    INFLUENCE_LEVELS,
)


# ── Test Data ─────────────────────────────────────────────────────

def _make_memory(memory_id, mtype="task", final_score=0.5):
    return {
        "memory_id": memory_id,
        "type": mtype,
        "category": "ai",
        "static_relevance": 0.45,
        "confidence_score": 0.3,
        "final_score": final_score,
        "match_reasons": ["relevance=0.45"],
        "evidence_level": "runtime_validated",
        "success_rate": 0.9,
        "tags": ["retrieval", "context", "prompt"],
    }


def _make_hypothesis(hypothesis_id, tags=None, guidance="", final_score=0.3):
    return {
        "memory_id": hypothesis_id,
        "type": "hypothesis",
        "category": "ai",
        "static_relevance": 0.35,
        "confidence_score": 0.1,
        "final_score": final_score,
        "match_reasons": ["relevance=0.35"],
        "evidence_level": "hypothesis",
        "success_rate": 0.0,
        "tags": tags or ["test", "hypothesis"],
        "guidance": guidance or "This hypothesis suggests testing a specific retrieval pattern.",
        "is_hypothesis": True,
    }


# ── Test A: Relevant hypothesis → correct attribution ─────────────

class TestHypothesisAttribution(unittest.TestCase):
    """Test that hypotheses are correctly attributed when agent references them."""

    def test_A_relevant_hypothesis_attributed(self):
        """A: Relevant hypothesis retrieved, injected, agent referenced → correct attribution."""
        memories = [_make_memory("S-001")]
        hypotheses = [
            _make_hypothesis("H-023", tags=["retrieval", "context", "dilution", "fallback"],
                             guidance="KeywordKnowledgeRetriever fallback returns all child knowledge points, diluting prompt context."),
        ]

        agent_response = (
            "## Impact Assessment\n\n"
            "The hypothesis H-023 about KeywordKnowledgeRetriever fallback was validated. "
            "The fallback returns all child knowledge points when no keyword match exists, "
            "which dilutes prompt context. This confirms the hypothesis is correct.\n\n"
            "Based on the hypothesis, I recommend removing or bounding the fallback."
        )

        result = _determine_influence(memories, hypotheses, agent_response)

        # Primary influence should be at least hypothesis_used
        self.assertIn(result["influence"],
                      ["hypothesis_used", "hypothesis_confirmed", "hypothesis_changed_decision"],
                      f"Expected hypothesis-level influence, got {result['influence']}")

        # H-023 should be in influence_breakdown with non-none influence
        self.assertIn("H-023", result["influence_breakdown"])
        self.assertNotEqual(result["influence_breakdown"]["H-023"]["influence"], "none")

        # Provenance should include H-023
        prov_ids = [p["memory_id"] for p in result["provenance"]]
        self.assertIn("H-023", prov_ids)

        # Established memory should still be confirmed
        self.assertIn("S-001", result["influence_breakdown"])
        self.assertEqual(result["influence_breakdown"]["S-001"]["influence"], "confirmation")

    def test_A2_hypothesis_confirmed_with_detection(self):
        """A2: Agent validates hypothesis and confirms it → hypothesis_confirmed."""
        memories = []
        hypotheses = [
            _make_hypothesis("H-024", tags=["cache", "TTL", "Redis", "session"],
                             guidance="Redis session TTL should be configurable to avoid stale sessions."),
        ]

        agent_response = (
            "## Analysis\n\n"
            "I tested the hypothesis H-024 about Redis session TTL configuration. "
            "The hypothesis is confirmed: the current implementation uses a hardcoded "
            "TTL of 24 hours which does cause stale sessions. The hypothesis correctly "
            "identifies the need for configurable TTL."
        )

        result = _determine_influence(memories, hypotheses, agent_response)

        self.assertIn("H-024", result["influence_breakdown"])
        self.assertIn(result["influence_breakdown"]["H-024"]["influence"],
                      ["hypothesis_used", "hypothesis_confirmed"])
        self.assertTrue(result["influence_breakdown"]["H-024"]["referenced"])


# ── Test B: Unrelated hypothesis → no influence ───────────────────

class TestUnrelatedHypothesis(unittest.TestCase):
    """Test that unrelated hypotheses do not produce influence."""

    def test_B_unrelated_hypothesis_no_influence(self):
        """B: Unrelated hypothesis injected but agent doesn't reference it → no influence."""
        memories = [_make_memory("T-005")]
        hypotheses = [
            _make_hypothesis("H-099", tags=["payment", "PCI-DSS", "compliance"],
                             guidance="Payment systems should use AES-256 for encryption."),
        ]

        agent_response = (
            "## Cache Analysis\n\n"
            "The Redis cache TTL should be set to 3600 seconds. "
            "This is unrelated to payment or PCI-DSS compliance. "
            "The focus is on cache configuration only."
        )

        result = _determine_influence(memories, hypotheses, agent_response)

        # H-099 should have no influence
        self.assertIn("H-099", result["influence_breakdown"])
        self.assertEqual(result["influence_breakdown"]["H-099"]["influence"], "none")

        # Primary influence should be confirmation (from established memory only)
        self.assertEqual(result["influence"], "confirmation")

        # Provenance should NOT include H-099
        prov_ids = [p["memory_id"] for p in result["provenance"]]
        self.assertNotIn("H-099", prov_ids)

    def test_B2_empty_response_no_hypothesis_influence(self):
        """B2: Empty agent response → hypotheses should not generate influence."""
        memories = []
        hypotheses = [
            _make_hypothesis("H-031", tags=["optimization", "query", "index"],
                             guidance="Add composite index for slow queries."),
        ]

        result = _determine_influence(memories, hypotheses, "")

        self.assertEqual(result["influence"], "none")
        self.assertIn("H-031", result["influence_breakdown"])
        self.assertEqual(result["influence_breakdown"]["H-031"]["influence"], "none")


# ── Test C: Established memory preserves original behavior ────────

class TestEstablishedMemoryBackwardCompat(unittest.TestCase):
    """Test that established memories keep the original behavior."""

    def test_C_established_memory_confirmation(self):
        """C: Established memory used → produces confirmation (same as before)."""
        memories = [_make_memory("S-001"), _make_memory("T-005")]
        hypotheses = []

        agent_response = (
            "## Task Analysis\n\n"
            "Using established patterns for this task. The approach is standard."
        )

        result = _determine_influence(memories, hypotheses, agent_response)

        self.assertEqual(result["influence"], "confirmation")
        self.assertIn("S-001", result["influence_breakdown"])
        self.assertIn("T-005", result["influence_breakdown"])
        self.assertEqual(result["influence_breakdown"]["S-001"]["influence"], "confirmation")
        self.assertEqual(result["influence_breakdown"]["T-005"]["influence"], "confirmation")

        # Provenance should include both memories
        prov_ids = [p["memory_id"] for p in result["provenance"]]
        self.assertIn("S-001", prov_ids)
        self.assertIn("T-005", prov_ids)

        # Memory type reflects actual type field (e.g., "task", "success", "failure")
        for record in result["provenance"]:
            self.assertIn(record["memory_type"], ["task", "success", "failure", "pattern", "anti-pattern"])

    def test_C2_no_memories_no_hypotheses_none(self):
        """C2: No memories, no hypotheses → influence is none (original behavior)."""
        result = _determine_influence([], [], "Some response")

        self.assertEqual(result["influence"], "none")
        self.assertEqual(len(result["provenance"]), 0)

    def test_C3_influence_field_present_for_backward_compat(self):
        """C3: The 'influence' field retains string values for backward compatibility."""
        memories = [_make_memory("E-005")]
        result = _determine_influence(memories, [], "Response")

        # Must be a string (not dict) for backward compatibility with existing code
        self.assertIsInstance(result["influence"], str)
        self.assertIn(result["influence"], INFLUENCE_LEVELS)


# ── Test D: F-NEG — no generic hypothesis influence ───────────────

class TestFalseNegativePrevention(unittest.TestCase):
    """Test that generic hypotheses do not produce false influence."""

    def test_D_generic_hypothesis_no_influence(self):
        """D: Generic hypothesis with no specific content match → no influence."""
        memories = []
        hypotheses = [
            _make_hypothesis("H-087", tags=["general", "best-practice", "common"],
                             guidance="Use best practices for software development."),
        ]

        agent_response = (
            "## Code Review\n\n"
            "The code follows standard patterns. No specific issues found. "
            "Everything looks good."
        )

        result = _determine_influence(memories, hypotheses, agent_response)

        # Generic hypothesis should not produce influence
        self.assertIn("H-087", result["influence_breakdown"])
        eng = result["influence_breakdown"]["H-087"]
        # The hypothesis should not have influence because the response is generic
        self.assertEqual(eng["influence"], "none",
                         f"Generic hypothesis should not produce influence, got {eng['influence']}")

    def test_D2_specific_hypothesis_but_no_match(self):
        """D2: Specific hypothesis but agent response is about different topic → no influence."""
        memories = []
        hypotheses = [
            _make_hypothesis("H-044", tags=["Redisson", "cache", "TTL", "config"],
                             guidance="RedissonConfig cache TTL should be externalized to configuration."),
        ]

        agent_response = (
            "## Database Migration\n\n"
            "The MySQL schema migration should be done in batches. "
            "No Redis or cache configuration is needed for this task."
        )

        result = _determine_influence(memories, hypotheses, agent_response)

        # H-044 should not produce influence because response is about DB, not Redis
        self.assertIn("H-044", result["influence_breakdown"])
        eng = result["influence_breakdown"]["H-044"]
        self.assertEqual(eng["influence"], "none",
                         f"Unrelated hypothesis should not produce influence, got {eng['influence']}")


# ── Test: Engagement Detection Edge Cases ─────────────────────────

class TestEngagementDetection(unittest.TestCase):
    """Test the _detect_hypothesis_engagement function directly."""

    def test_explicit_hypothesis_id_mention(self):
        """Agent explicitly mentions H-xxx ID → referenced."""
        hypotheses = [_make_hypothesis("H-041", tags=["Redisson", "cache", "TTL"])]
        response = "The hypothesis H-041 about RedissonConfig cache TTL is correct."

        eng = _detect_hypothesis_engagement(response, hypotheses)

        self.assertIn("H-041", eng)
        self.assertTrue(eng["H-041"]["id_mentioned"])
        self.assertNotEqual(eng["H-041"]["engagement_level"], "none")

    def test_semantic_match_no_explicit_id(self):
        """Agent uses hypothesis terms without mentioning ID → semantic match."""
        hypotheses = [_make_hypothesis("H-025", tags=["fallback", "keyword", "retriever", "context"],
                                       guidance="Keyword retriever fallback mechanism causes context dilution.")]
        response = (
            "The keyword retriever fallback mechanism returns all child points "
            "when no match exists, causing context dilution. This should be fixed."
        )

        eng = _detect_hypothesis_engagement(response, hypotheses)

        self.assertIn("H-025", eng)
        self.assertTrue(eng["H-025"]["referenced"])

    def test_no_match(self):
        """Agent response completely unrelated → no engagement."""
        hypotheses = [_make_hypothesis("H-039", tags=["cache", "TTL", "Redis"])]
        response = "The database query uses proper indexing."

        eng = _detect_hypothesis_engagement(response, hypotheses)

        self.assertIn("H-039", eng)
        self.assertFalse(eng["H-039"]["referenced"])
        self.assertEqual(eng["H-039"]["engagement_level"], "none")

    def test_changed_decision_detection(self):
        """Agent explicitly states hypothesis changed decision → hypothesis_changed_decision."""
        hypotheses = [_make_hypothesis("H-027", tags=["decision", "architecture"],
                                       guidance="Consider microservices for scalability.")]
        response = (
            "The hypothesis H-027 about microservices changed my decision. "
            "I had initially planned a monolith, but after reviewing the hypothesis "
            "I revised my approach to use microservices."
        )

        eng = _detect_hypothesis_engagement(response, hypotheses)

        self.assertIn("H-027", eng)
        self.assertTrue(eng["H-027"]["changed_decision"])


# ── Test: Provenance Completeness ─────────────────────────────────

class TestProvenanceCompleteness(unittest.TestCase):
    """Test that provenance records contain all required fields."""

    REQUIRED_PROVENANCE_FIELDS = {
        "memory_id", "memory_type", "retrieval_score",
        "injection_format", "agent_reference",
    }

    def test_provenance_has_required_fields(self):
        """Every provenance record must have all required fields."""
        memories = [_make_memory("S-001")]
        hypotheses = [
            _make_hypothesis("H-023", tags=["retrieval", "context"],
                             guidance="Retrieval context should be bounded."),
        ]

        agent_response = "H-023 about retrieval context is confirmed. The approach is valid."

        result = _determine_influence(memories, hypotheses, agent_response)

        for record in result["provenance"]:
            for field in self.REQUIRED_PROVENANCE_FIELDS:
                self.assertIn(field, record,
                              f"Provenance record missing field '{field}': {record}")

    def test_provenance_memory_type_correct(self):
        """Provenance should correctly identify hypothesis vs non-hypothesis types."""
        memories = [_make_memory("S-001")]
        hypotheses = [
            _make_hypothesis("H-023", tags=["retrieval"],
                             guidance="Retrieval hypothesis test."),
        ]

        agent_response = "H-023 is validated. The retrieval approach works."

        result = _determine_influence(memories, hypotheses, agent_response)

        for record in result["provenance"]:
            mid = record["memory_id"]
            if mid.startswith("H-"):
                self.assertEqual(record["memory_type"], "hypothesis")
                self.assertEqual(record["injection_format"], "hypothesis_injection")
            else:
                # Non-hypothesis memories keep their actual type (task, success, etc.)
                self.assertNotEqual(record["memory_type"], "hypothesis")
                self.assertEqual(record["injection_format"], "semantic_guidance")


if __name__ == "__main__":
    unittest.main()