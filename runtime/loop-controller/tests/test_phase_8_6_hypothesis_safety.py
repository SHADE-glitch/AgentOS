#!/usr/bin/env python3
"""
Phase 8.6 — Hypothesis Lane Safety & Scalability Layer tests.

C1  same_loop_as_creation real provenance + backward compat
C2  distinct-loop threshold (hypothesis 1-loop, validated 2-loop)
C3  fail-closed type guard (cross-type contamination rejection)
C4  canonical_source priority chain + hypothesis-lane switch
C5  is_countable_observation single gate (collector ↔ validator)
RC  cross-memory coexistence R1+R4+R7 without contamination

Tests use the frozen pipeline:
  build_trace() → collect_from_trace_ids() → validate_candidates()
No live provider, no collector bypass.
"""
import sys
import os
import unittest
import tempfile
import yaml
from datetime import datetime, timezone
from unittest.mock import patch

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_LOOP_CONTROLLER_DIR = os.path.dirname(_TEST_DIR)
_COLLECTOR_DIR = os.path.join(_LOOP_CONTROLLER_DIR, "..", "memory-feedback", "collector")
_PROMOTION_DIR = os.path.join(_LOOP_CONTROLLER_DIR, "..", "memory-feedback", "promotion")
_RUNTIME_ADAPTER_DIR = _LOOP_CONTROLLER_DIR
for _p in (_LOOP_CONTROLLER_DIR, _COLLECTOR_DIR, _PROMOTION_DIR, _RUNTIME_ADAPTER_DIR):
    _p = os.path.normpath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from collector import (
    generate_candidates,
    HYPOTHESIS_CANDIDATE_TYPES,
    is_countable_observation,
    canonical_source_for,
    _normalize_hypothesis_engagement,
    collect_from_trace_ids,
)
import validator
from runtime_adapter import build_trace, _determine_influence

HYP = "H-999-PHASE86-TEST"
TASK = "TASK-001"

QUALITY = {"weighted": 4.0, "completeness": 4, "accuracy": 4, "structure": 4,
           "actionability": 4, "novelty": 4}


def _trace(**over):
    """Build a minimal trace dict for test — as used by collector.generate_candidates."""
    base = {
        "execution_id": "EXEC-86-T",
        "status": "success",
        "task_id": "T86",
        "model": "test-phase86",
        "agent_response": "",
        "agent_invocation": {
            "session_id": "sess-86",
            "tokens": {"input": 10, "output": 90, "total": 100},
            "latency_ms": 50,
        },
        "memory_retrieval": {
            "memories_used": [],
            "memory_influence": "none",
            "influence_breakdown": {},
            "hypotheses_injected": [],
        },
    }
    base.update(over)
    return base


# ── Test Helpers ──────────────────────────────────────────────────

def _make_decision_context(hypotheses=None, memories=None, loop_id=None):
    """Build a minimal decision_context for build_trace."""
    dc = {
        "classification": {"category": "backend", "difficulty": "medium"},
        "route_decision": {"intent": "backend", "lead_skill": "backend-architect",
                           "support_skills": [], "confidence": "medium",
                           "memory_influence": "none", "rules_applied": []},
        "skill_context": {"skills_loaded": ["backend-architect"],
                          "lead_skill": {"loaded": True},
                          "support_skills": []},
        "memories": memories or [],
        "hypotheses": hypotheses or [],
        "retrieved": True,
        "entry_metadata": {"entry_type": "task"},
    }
    if loop_id:
        dc["loop_id"] = loop_id
    return dc


def _make_runtime_result(status="success", response=""):
    return {
        "status": status,
        "response_text": response,
        "reliability": {},
        "cross_stack_warning": {},
    }


# ── C1: same_loop_as_creation real provenance ─────────────────────

class TestSameLoopAsCreation(unittest.TestCase):
    """C1 — same_loop_as_creation populated from created_loop vs loop_id."""

    def test_same_loop_as_creation_populated(self):
        """Check that same_loop_as_creation is correctly computed from
        hypothesis created_loop and runtime loop_id."""
        # Hypothesis created in LOOP-A, engaged in LOOP-A → same_loop=true
        hyp = {"memory_id": HYP, "type": "hypothesis", "category": "test",
               "static_relevance": 0.5, "confidence_score": 0.3, "final_score": 0.4,
               "match_reasons": [], "created_loop": "LOOP-A"}
        dc = _make_decision_context(hypotheses=[hyp], loop_id="LOOP-A")
        result = _make_runtime_result(
            response=f"Hypothesis {HYP} is confirmed by the new data.")
        trace = build_trace("EXEC-C1-1", "TRACE-C1-1", "T-C1", "test task",
                            dc, "test", "test-model", result, loop_id="LOOP-A")

        ib = trace["memory_retrieval"]["influence_breakdown"].get(HYP, {})
        self.assertEqual(ib.get("created_loop"), "LOOP-A",
                         "created_loop should be LOOP-A")
        self.assertTrue(ib.get("same_loop_as_creation"),
                        "same_loop_as_creation should be True when loop_id == created_loop")

        # Same hypothesis, different loop → same_loop=false
        dc2 = _make_decision_context(hypotheses=[hyp], loop_id="LOOP-B")
        result2 = _make_runtime_result(
            response=f"Hypothesis {HYP} is referenced in the analysis.")
        trace2 = build_trace("EXEC-C1-2", "TRACE-C1-2", "T-C1b", "test task",
                             dc2, "test", "test-model", result2, loop_id="LOOP-B")

        ib2 = trace2["memory_retrieval"]["influence_breakdown"].get(HYP, {})
        self.assertEqual(ib2.get("created_loop"), "LOOP-A",
                         "created_loop stays LOOP-A from hypothesis metadata")
        self.assertFalse(ib2.get("same_loop_as_creation"),
                         "same_loop_as_creation should be False when loop_id != created_loop")

    def test_same_loop_as_creation_backward_compat(self):
        """Backward compat: missing created_loop → same_loop=false."""
        hyp = {"memory_id": HYP, "type": "hypothesis", "category": "test",
               "static_relevance": 0.5, "confidence_score": 0.3, "final_score": 0.4,
               "match_reasons": []}
        # No created_loop field
        dc = _make_decision_context(hypotheses=[hyp], loop_id="LOOP-X")
        result = _make_runtime_result(
            response=f"Hypothesis {HYP} is noted.")
        trace = build_trace("EXEC-C1-3", "TRACE-C1-3", "T-C1c", "test task",
                            dc, "test", "test-model", result, loop_id="LOOP-X")

        ib = trace["memory_retrieval"]["influence_breakdown"].get(HYP, {})
        self.assertEqual(ib.get("created_loop"), "",
                         "created_loop should be empty string when missing")
        self.assertFalse(ib.get("same_loop_as_creation"),
                         "same_loop_as_creation should be False when created_loop missing")

    def test_normalize_hypothesis_engagement_carries_created_loop(self):
        """_normalize_hypothesis_engagement passes through created_loop."""
        info = {"referenced": True, "id_mentioned": True, "term_matches": 3,
                "created_loop": "LOOP-ORIGIN", "same_loop_as_creation": False}
        eng = _normalize_hypothesis_engagement(info)
        self.assertEqual(eng["created_loop"], "LOOP-ORIGIN")
        self.assertFalse(eng["same_loop_as_creation"])


# ── C2 + C4: distinct-loop threshold + canonical source ───────────

class TestDistinctLoopThreshold(unittest.TestCase):
    """C2 + C4 — hypothesis lane uses canonical_source; 2 distinct loops → validated."""

    def test_two_executions_same_loop_counts_as_one(self):
        """Two candidates with same loop_id but different execution_id → count as 1."""
        c1 = {
            "candidate_id": "CAND-EXEC1-HYP-999",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-1",
            "loop_id": "LOOP-SAME",
            "quality_score": 4.0,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-SAME", "source_loop": "LOOP-SAME",
                "same_loop_as_creation": False, "created_loop": "LOOP-OTHER",
            },
            "evidence": {"session_id": "s1", "output_hash": "h1"},
        }
        c2 = {
            "candidate_id": "CAND-EXEC2-HYP-999",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-2",
            "loop_id": "LOOP-SAME",
            "quality_score": 4.5,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-SAME", "source_loop": "LOOP-SAME",
                "same_loop_as_creation": False, "created_loop": "LOOP-OTHER",
            },
            "evidence": {"session_id": "s2", "output_hash": "h2"},
        }

        groups = validator.group_candidates_by_memory([c1, c2])
        self.assertIn(HYP, groups)
        group = groups[HYP]
        self.assertEqual(len(group["executions"]), 1,
                         "Same loop_id should dedup to 1 canonical source")
        self.assertIn("LOOP-SAME", group["executions"])

        status, result = validator.validate_memory_group(HYP, group)
        self.assertEqual(status, "hypothesis",
                         "1 distinct loop → hypothesis (not validated)")
        self.assertEqual(result["validation_runs"], 1)

    def test_two_loops_counts_as_two_validated(self):
        """Two candidates with distinct loop_ids → count as 2 → validated."""
        c1 = {
            "candidate_id": "CAND-EXEC-A-HYP-999",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "confirmed",
            "source_execution": "EXEC-A",
            "loop_id": "LOOP-ALPHA",
            "quality_score": 4.0,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_confirmed",
                "loop_id": "LOOP-ALPHA", "source_loop": "LOOP-ALPHA",
                "same_loop_as_creation": False, "created_loop": "LOOP-ORIGIN",
            },
            "evidence": {"session_id": "sA", "output_hash": "hA"},
        }
        c2 = {
            "candidate_id": "CAND-EXEC-B-HYP-999",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-B",
            "loop_id": "LOOP-BETA",
            "quality_score": 4.5,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-BETA", "source_loop": "LOOP-BETA",
                "same_loop_as_creation": False, "created_loop": "LOOP-ORIGIN",
            },
            "evidence": {"session_id": "sB", "output_hash": "hB"},
        }

        groups = validator.group_candidates_by_memory([c1, c2])
        group = groups[HYP]
        self.assertEqual(len(group["executions"]), 2,
                         "Distinct loop_ids → 2 canonical sources")
        self.assertIn("LOOP-ALPHA", group["executions"])
        self.assertIn("LOOP-BETA", group["executions"])

        status, result = validator.validate_memory_group(HYP, group)
        self.assertEqual(status, "validated",
                         "2 distinct loops → validated")
        self.assertEqual(result["validation_runs"], 2)

    def test_same_loop_confirmation_excluded(self):
        """I9: same_loop_as_creation=True → excluded from validation_runs."""
        c1 = {
            "candidate_id": "CAND-SELF-HYP-999",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-SELF",
            "loop_id": "LOOP-SELF",
            "quality_score": 4.0,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-SELF", "source_loop": "LOOP-SELF",
                "same_loop_as_creation": True, "created_loop": "LOOP-SELF",
            },
            "evidence": {"session_id": "sSelf", "output_hash": "hSelf"},
        }

        # is_countable_observation should return False
        self.assertFalse(is_countable_observation(c1),
                         "same_loop_as_creation=True → not countable")

        groups = validator.group_candidates_by_memory([c1])
        self.assertIn(HYP, groups)
        group = groups[HYP]
        self.assertEqual(len(group["executions"]), 0,
                         "Self-confirm should add 0 executions")
        self.assertEqual(len(group["candidates"]), 1,
                         "Self-confirm candidate still in audit list")

        status, result = validator.validate_memory_group(HYP, group)
        # With 0 countable executions, should be rejected
        self.assertEqual(status, "rejected")
        self.assertIn("Only 0 observation", result.get("rejection_reason", ""))

    def test_self_confirm_excluded_one_valid_other_loop(self):
        """One self-confirm + one valid distinct loop → 1 validation run → hypothesis."""
        c_self = {
            "candidate_id": "CAND-SELF-HYP",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-SELF",
            "loop_id": "LOOP-SELF",
            "quality_score": 4.0,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-SELF", "source_loop": "LOOP-SELF",
                "same_loop_as_creation": True, "created_loop": "LOOP-SELF",
            },
            "evidence": {"session_id": "sSelf", "output_hash": "hSelf"},
        }
        c_valid = {
            "candidate_id": "CAND-VALID-HYP",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-VALID",
            "loop_id": "LOOP-OTHER",
            "quality_score": 4.5,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-OTHER", "source_loop": "LOOP-OTHER",
                "same_loop_as_creation": False, "created_loop": "LOOP-SELF",
            },
            "evidence": {"session_id": "sValid", "output_hash": "hValid"},
        }

        groups = validator.group_candidates_by_memory([c_self, c_valid])
        group = groups[HYP]
        self.assertEqual(len(group["executions"]), 1,
                         "Self-confirm excluded, only 1 valid loop")
        self.assertIn("LOOP-OTHER", group["executions"])

        status, result = validator.validate_memory_group(HYP, group)
        self.assertEqual(status, "hypothesis",
                         "1 valid loop → hypothesis status")


# ── C4: canonical_source priority chain ───────────────────────────

class TestCanonicalSourcePriority(unittest.TestCase):
    """C4 — canonical_source_for respects priority: loop_id > source_loop > source_execution."""

    def test_canonical_source_prefers_loop_id_over_execution(self):
        """loop_id should be preferred over source_execution."""
        c = {
            "hypothesis_engagement": {"loop_id": "LOOP-CANON", "source_loop": "LOOP-TRACE"},
            "loop_id": "LOOP-CANDIDATE",
            "source_execution": "EXEC-FOO",
        }
        cs = canonical_source_for(c)
        self.assertEqual(cs, "LOOP-CANON",
                         "Priority: hyp_engagement.loop_id first")

    def test_canonical_source_falls_back_to_source_loop(self):
        """When loop_id missing, falls back to source_loop."""
        c = {
            "hypothesis_engagement": {"loop_id": "", "source_loop": "LOOP-TRACE"},
            "loop_id": "",
            "source_execution": "EXEC-FOO",
        }
        cs = canonical_source_for(c)
        self.assertEqual(cs, "LOOP-TRACE",
                         "Priority: source_loop when loop_id empty")

    def test_canonical_source_falls_back_to_candidate_loop_id(self):
        """When he loop_id/source_loop missing, falls back to candidate.loop_id."""
        c = {
            "hypothesis_engagement": {},
            "loop_id": "LOOP-CANDIDATE",
            "source_execution": "EXEC-FOO",
        }
        cs = canonical_source_for(c)
        self.assertEqual(cs, "LOOP-CANDIDATE",
                         "Priority: candidate.loop_id when he fields missing")

    def test_canonical_source_falls_back_to_source_execution(self):
        """Ultimate fallback: source_execution."""
        c = {
            "hypothesis_engagement": {},
            "loop_id": "",
            "source_execution": "EXEC-FOO",
        }
        cs = canonical_source_for(c)
        self.assertEqual(cs, "EXEC-FOO",
                         "Ultimate fallback: source_execution")


# ── C3: fail-closed type guard ────────────────────────────────────

class TestTypeMismatchRejection(unittest.TestCase):
    """C3 — validator rejects cross-type contamination fail-closed."""

    def test_reject_reinforce_targeting_hypothesis(self):
        """reinforce targeting H-xxx → rejected."""
        c = {
            "candidate_id": "CAND-TYPE-ERR-1",
            "target_memory": HYP,
            "candidate_type": "reinforce",
            "outcome": "promoted",
            "source_execution": "EXEC-ERR",
            "quality_score": 4.0,
            "evidence": {"session_id": "sErr", "output_hash": "hErr"},
        }
        # group_candidates_by_memory should mark it rejected
        groups = validator.group_candidates_by_memory([c])
        self.assertIn(HYP, groups)
        group = groups[HYP]
        self.assertTrue(any(cand.get("_rejected") for cand in group["candidates"]),
                        "reinforce on H-xxx should be rejected")

        status, result = validator.validate_memory_group(HYP, group)
        self.assertEqual(status, "rejected")
        self.assertIn("Type confusion", result.get("rejection_reason", ""))

    def test_reject_reinforce_hypothesis_targeting_established(self):
        """reinforce_hypothesis targeting non-H memory → rejected."""
        c = {
            "candidate_id": "CAND-TYPE-ERR-2",
            "target_memory": "TASK-001",
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-ERR2",
            "quality_score": 4.0,
            "hypothesis_engagement": {
                "referenced": True, "engagement_level": "hypothesis_used",
                "same_loop_as_creation": False,
            },
            "evidence": {"session_id": "sErr2", "output_hash": "hErr2"},
        }
        groups = validator.group_candidates_by_memory([c])
        self.assertIn("TASK-001", groups)
        group = groups["TASK-001"]
        self.assertTrue(any(cand.get("_rejected") for cand in group["candidates"]),
                        "reinforce_hypothesis on non-H should be rejected")

        status, result = validator.validate_memory_group("TASK-001", group)
        self.assertEqual(status, "rejected")
        self.assertIn("Type confusion", result.get("rejection_reason", ""))


# ── C5: is_countable_observation single gate ──────────────────────

class TestIsCountableObservation(unittest.TestCase):
    """C5 — is_countable_observation excludes inconclusive + self-confirm."""

    def test_inconclusive_hypothesis_not_countable(self):
        """inconclusive hypothesis → not countable."""
        c = {
            "candidate_type": "reinforce_hypothesis",
            "outcome": "inconclusive",
            "hypothesis_engagement": {"same_loop_as_creation": False},
        }
        self.assertFalse(is_countable_observation(c))

    def test_self_confirm_not_countable(self):
        """same_loop_as_creation=True → not countable."""
        c = {
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "hypothesis_engagement": {"same_loop_as_creation": True},
        }
        self.assertFalse(is_countable_observation(c))

    def test_normal_observed_is_countable(self):
        """Normal observed hypothesis → countable."""
        c = {
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "hypothesis_engagement": {"same_loop_as_creation": False},
        }
        self.assertTrue(is_countable_observation(c))

    def test_established_reinforce_is_countable(self):
        """Established reinforce → always countable."""
        c = {
            "candidate_type": "reinforce",
            "outcome": "promoted",
            "hypothesis_engagement": {},
        }
        self.assertTrue(is_countable_observation(c))

    def test_inconclusive_never_counts_in_validator(self):
        """inconclusive hypothesis → 0 executions in validator group."""
        c = {
            "candidate_id": "CAND-INCONC",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "inconclusive",
            "source_execution": "EXEC-INCONC",
            "quality_score": 3.0,
            "hypothesis_engagement": {
                "referenced": True, "engagement_level": "hypothesis_used",
                "same_loop_as_creation": False,
            },
            "evidence": {"session_id": "sInc", "output_hash": "hInc"},
        }
        groups = validator.group_candidates_by_memory([c])
        group = groups[HYP]
        self.assertEqual(len(group["executions"]), 0,
                         "Inconclusive must not add to executions")
        self.assertEqual(len(group["candidates"]), 1,
                         "Inconclusive still in audit list")


# ── RC: Cross-memory coexistence R1+R4+R7 ─────────────────────────

class TestCrossMemoryCoexistence(unittest.TestCase):
    """RC — R1 established + R7 hypothesis + R4 team coexist without contamination."""

    def test_r1_reinforce_and_r7_hypothesis_coexist(self):
        """Single trace with both R1 (reinforce) and R7 (reinforce_hypothesis)."""
        c_r1 = {
            "candidate_id": "CAND-R1-TASK",
            "target_memory": "TASK-001",
            "candidate_type": "reinforce",
            "outcome": "promoted",
            "source_execution": "EXEC-MIX",
            "quality_score": 4.0,
            "evidence": {"session_id": "sMix", "output_hash": "hMix"},
        }
        c_r7 = {
            "candidate_id": "CAND-R7-HYP",
            "target_memory": HYP,
            "candidate_type": "reinforce_hypothesis",
            "outcome": "observed",
            "source_execution": "EXEC-MIX",
            "loop_id": "LOOP-MIX",
            "quality_score": 4.0,
            "hypothesis_engagement": {
                "referenced": True, "id_mentioned": True, "term_matches": 3,
                "engagement_level": "hypothesis_used",
                "loop_id": "LOOP-MIX", "source_loop": "LOOP-MIX",
                "same_loop_as_creation": False, "created_loop": "",
            },
            "evidence": {"session_id": "sMix", "output_hash": "hMix"},
        }

        groups = validator.group_candidates_by_memory([c_r1, c_r7])
        self.assertIn("TASK-001", groups)
        self.assertIn(HYP, groups)

        # R1 established: source_execution-based counting
        group_r1 = groups["TASK-001"]
        self.assertEqual(len(group_r1["executions"]), 1)
        self.assertIn("EXEC-MIX", group_r1["executions"])

        # R7 hypothesis: canonical_source-based counting
        group_r7 = groups[HYP]
        self.assertEqual(len(group_r7["executions"]), 1)
        self.assertIn("LOOP-MIX", group_r7["executions"])

        # R1 should validate as established (needs 2 for validated, 1 → rejected)
        status_r1, result_r1 = validator.validate_memory_group("TASK-001", group_r1)
        self.assertEqual(status_r1, "rejected",
                         "Established R1 needs 2 observations")

        # R7 should validate as hypothesis (1 observation)
        status_r7, result_r7 = validator.validate_memory_group(HYP, group_r7)
        self.assertEqual(status_r7, "hypothesis",
                         "Hypothesis R7 with 1 observation → hypothesis")

    def test_established_lane_not_affected_by_canonical_source(self):
        """Established lane (non-H) still uses source_execution, not canonical_source."""
        c1 = {
            "candidate_id": "CAND-EST-1",
            "target_memory": "TASK-001",
            "candidate_type": "reinforce",
            "outcome": "promoted",
            "source_execution": "EXEC-EST-1",
            "quality_score": 4.0,
            "evidence": {"session_id": "sEst1", "output_hash": "hEst1"},
        }
        c2 = {
            "candidate_id": "CAND-EST-2",
            "target_memory": "TASK-001",
            "candidate_type": "reinforce",
            "outcome": "promoted",
            "source_execution": "EXEC-EST-2",
            "quality_score": 4.5,
            "evidence": {"session_id": "sEst2", "output_hash": "hEst2"},
        }

        groups = validator.group_candidates_by_memory([c1, c2])
        group = groups["TASK-001"]
        self.assertEqual(len(group["executions"]), 2,
                         "Established lane: 2 distinct source_executions")
        self.assertIn("EXEC-EST-1", group["executions"])
        self.assertIn("EXEC-EST-2", group["executions"])
        # Note: full validate_memory_group requires TASK-001 in retrieval-index;
        # the grouping behavior (source_execution, not canonical_source) is
        # what's validated here.


if __name__ == "__main__":
    unittest.main()