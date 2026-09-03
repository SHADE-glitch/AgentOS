#!/usr/bin/env python3
"""
Phase 8.4 — Hypothesis Reinforcement Lane tests.

Validates the Phase 8.4 implementation across focus areas:
  A. classify_hypothesis_engagement() classification + provenance (I1-I8)
  B. R7 trace candidate generation (collector.generate_candidates)
  C. R4 multi-agent team candidate path (team_result_collector)
  D. weaken_hypothesis rejection (validator)
  E. validator grouping: inconclusive never inflates validation_runs;
     promotion safety (1 obs = hypothesis, never direct-promote)
  F. negative evidence / independence (target memory identity never renamed)

These tests are deterministic and call the classifier, R7/R4 rules, and the
validator grouping/validation functions directly — no real runtime/traces.
"""

import sys
import os
import unittest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_LOOP_CONTROLLER_DIR = os.path.dirname(_TEST_DIR)
_COLLECTOR_DIR = os.path.join(
    _LOOP_CONTROLLER_DIR, "..", "memory-feedback", "collector")
_PROMOTION_DIR = os.path.join(
    _LOOP_CONTROLLER_DIR, "..", "memory-feedback", "promotion")
for _p in (_LOOP_CONTROLLER_DIR, _COLLECTOR_DIR, _PROMOTION_DIR):
    _p = os.path.normpath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from collector import (
    classify_hypothesis_engagement,
    generate_candidates,
    HYPOTHESIS_CANDIDATE_TYPES,
    _normalize_hypothesis_engagement,
)
from team_result_collector import TeamResultCollector
import validator

HYP = "H-001-STATESTORE"

QUALITY = {
    "weighted": 4.0,
    "completeness": 4,
    "accuracy": 4,
    "structure": 4,
    "actionability": 4,
    "novelty": 4,
}


def _trace(**over):
    base = {
        "execution_id": "E8",
        "status": "success",
        "task_id": "T8",
        "model": "test",
        "agent_response": "",
        "agent_invocation": {
            "session_id": "S8",
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


def _src(**over):
    base = {
        "loop_id": "LOOP-E",
        "team_id": "TEAM-E",
        "team_result": {
            "status": "success",
            "lead_output": {
                "agent": "database-engineer",
                "output": "",
                "tokens": {"total": 200},
                "latency_ms": 100,
            },
        },
        "task_cards": [],
        "hypotheses_injected": [],
    }
    base.update(over)
    return base


def _hyp_candidates(cands):
    return [c for c in cands if c.get("candidate_type") in HYPOTHESIS_CANDIDATE_TYPES]


# ── A. classify_hypothesis_engagement() ───────────────────────────

class TestClassifyHypothesisEngagement(unittest.TestCase):

    def test_1_confirmed_changed_decision(self):
        info = {"referenced": True, "influence": "hypothesis_used",
                "changed_decision": True, "id_mentioned": True, "term_matches": 1}
        ctype, outcome, _ = classify_hypothesis_engagement("x", HYP, info)
        self.assertEqual(ctype, "reinforce_hypothesis")
        self.assertEqual(outcome, "confirmed")

    def test_2_confirmed_high_level(self):
        info = {"referenced": True, "influence": "hypothesis_confirmed",
                "changed_decision": False, "id_mentioned": True, "term_matches": 2}
        ctype, outcome, _ = classify_hypothesis_engagement("x", HYP, info)
        self.assertEqual(ctype, "reinforce_hypothesis")
        self.assertEqual(outcome, "confirmed")

    def test_3_observed_strong_terms(self):
        info = {"referenced": True, "influence": "hypothesis_used",
                "id_mentioned": False, "term_matches": 3}
        ctype, outcome, _ = classify_hypothesis_engagement("x", HYP, info)
        self.assertEqual(ctype, "reinforce_hypothesis")
        self.assertEqual(outcome, "observed")

    def test_4_weak_mention_inconclusive(self):
        info = {"referenced": True, "influence": "hypothesis_used",
                "id_mentioned": False, "term_matches": 0}
        ctype, outcome, _ = classify_hypothesis_engagement("x", HYP, info)
        self.assertEqual(ctype, "reinforce_hypothesis")
        self.assertEqual(outcome, "inconclusive")

    def test_5_not_referenced_abstains(self):
        info = {"referenced": False, "influence": "hypothesis_used"}
        ctype, outcome, _ = classify_hypothesis_engagement("x", HYP, info)
        self.assertIsNone(ctype)
        self.assertEqual(outcome, "inconclusive")

    def test_6_refuted_weaken(self):
        info = {"referenced": True, "influence": "hypothesis_used",
                "id_mentioned": True, "term_matches": 1}
        text = "The hypothesis H-001 was refuted by our tests."
        ctype, outcome, _ = classify_hypothesis_engagement(text, HYP, info)
        self.assertEqual(ctype, "weaken_hypothesis")
        self.assertEqual(outcome, "refuted")

    def test_7_provenance_complete_audit_keys(self):
        prov = _normalize_hypothesis_engagement(
            {"referenced": True, "term_matches": 2, "changed_decision": True})
        self.assertEqual(
            set(prov.keys()),
            {"referenced", "engagement_level", "term_matches", "id_mentioned",
             "changed_decision", "same_loop_as_creation",
             "shared_context_with_other_agents",
             "created_loop"},  # Phase 8.6-C1: created_loop provenance
        )
        self.assertTrue(prov["referenced"])
        self.assertTrue(prov["changed_decision"])
        self.assertEqual(prov["term_matches"], 2)

    def test_8_candidate_types_constant(self):
        self.assertEqual(HYPOTHESIS_CANDIDATE_TYPES,
                         ("reinforce_hypothesis", "weaken_hypothesis"))

    def test_9_abstention_governs_over_refutation(self):
        info = {"referenced": False, "id_mentioned": True}
        text = "The hypothesis H-001 was refuted by our tests."
        ctype, outcome, _ = classify_hypothesis_engagement(text, HYP, info)
        self.assertIsNone(ctype)
        self.assertEqual(outcome, "inconclusive")

    def test_10_observed_requires_id_or_terms(self):
        info = {"referenced": True, "influence": "hypothesis_used",
                "id_mentioned": False, "term_matches": 2}
        ctype, outcome, _ = classify_hypothesis_engagement("x", HYP, info)
        self.assertEqual(outcome, "inconclusive")


# ── B. R7 trace path (collector.generate_candidates) ──────────────

class TestR7TracePath(unittest.TestCase):

    def test_11_confirmed_emits_reinforce_candidate(self):
        tr = _trace(
            agent_response="Confirmed hypothesis H-001 with the code review.",
            memory_retrieval={
                "memories_used": [],
                "memory_influence": "none",
                "hypotheses_injected": [HYP],
                "influence_breakdown": {
                    HYP: {"type": "hypothesis", "influence": "hypothesis_confirmed",
                          "memory_id": HYP, "referenced": True,
                          "id_mentioned": True,
                          "term_matches": 2, "changed_decision": True},
                },
            },
        )
        cands = _hyp_candidates(generate_candidates(tr, QUALITY))
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["candidate_type"], "reinforce_hypothesis")
        self.assertEqual(cands[0]["target_memory"], HYP)
        self.assertEqual(cands[0]["outcome"], "confirmed")
        self.assertIn("hypothesis_engagement", cands[0])

    def test_12_candidate_full_provenance(self):
        tr = _trace(
            agent_response="Hypothesis confirmed.",
            memory_retrieval={
                "memories_used": [],
                "memory_influence": "none",
                "hypotheses_injected": [HYP],
                "influence_breakdown": {
                    HYP: {"type": "hypothesis", "influence": "hypothesis_changed_decision",
                          "memory_id": HYP, "referenced": True,
                          "id_mentioned": True,
                          "term_matches": 1, "changed_decision": True},
                },
            },
        )
        cand = _hyp_candidates(generate_candidates(tr, QUALITY))[0]
        prov = cand["hypothesis_engagement"]
        self.assertEqual(prov["engagement_level"], "hypothesis_changed_decision")
        self.assertTrue(prov["changed_decision"])
        self.assertTrue(prov["id_mentioned"])

    def test_13_not_referenced_abstains(self):
        tr = _trace(
            agent_response="Just did the schema migration.",
            memory_retrieval={
                "memories_used": [],
                "memory_influence": "none",
                "hypotheses_injected": [HYP],
                "influence_breakdown": {
                    HYP: {"type": "hypothesis", "influence": "none",
                          "memory_id": HYP, "referenced": False,
                          "id_mentioned": False, "term_matches": 0},
                },
            },
        )
        self.assertEqual(_hyp_candidates(generate_candidates(tr, QUALITY)), [])

    def test_14_uninjected_hyp_identity_skipped(self):
        tr = _trace(
            agent_response="Confirmed hypothesis H-001.",
            memory_retrieval={
                "memories_used": [],
                "memory_influence": "none",
                "hypotheses_injected": ["H-OTHER"],
                "influence_breakdown": {
                    HYP: {"type": "hypothesis", "influence": "hypothesis_confirmed",
                          "memory_id": HYP, "id_mentioned": True,
                          "term_matches": 2, "changed_decision": True},
                },
            },
        )
        self.assertEqual(_hyp_candidates(generate_candidates(tr, QUALITY)), [])

    def test_15_hyp_in_memused_not_doubled(self):
        tr = _trace(
            agent_response="Confirmed hypothesis H-001.",
            memory_retrieval={
                "memories_used": [HYP],
                "memory_influence": "confirmation",
                "hypotheses_injected": [HYP],
                "influence_breakdown": {
                    HYP: {"type": "hypothesis", "influence": "hypothesis_confirmed",
                          "memory_id": HYP, "id_mentioned": True,
                          "term_matches": 2, "changed_decision": True},
                },
            },
        )
        cands = generate_candidates(tr, QUALITY)
        self.assertEqual(_hyp_candidates(cands), [])
        self.assertTrue(any(c["candidate_type"] == "reinforce"
                            and c["target_memory"] == HYP for c in cands))

    def test_16_r7_refuted_emits_weaken(self):
        tr = _trace(
            agent_response="Hypothesis H-001 was refuted by the benchmark.",
            memory_retrieval={
                "memories_used": [],
                "memory_influence": "none",
                "hypotheses_injected": [HYP],
                "influence_breakdown": {
                    HYP: {"type": "hypothesis", "influence": "hypothesis_used",
                          "memory_id": HYP, "referenced": True,
                          "id_mentioned": True,
                          "term_matches": 1, "changed_decision": False},
                },
            },
        )
        cand = _hyp_candidates(generate_candidates(tr, QUALITY))[0]
        self.assertEqual(cand["candidate_type"], "weaken_hypothesis")
        self.assertEqual(cand["outcome"], "refuted")


# ── C. R4 multi-agent team path (team_result_collector) ───────────

class TestR4TeamPath(unittest.TestCase):
    def setUp(self):
        self.collector = TeamResultCollector()

    def test_17_confirmed_reinforce_candidate(self):
        src = _src(
            team_result={"status": "success", "completed_count": 1,
                         "failed_count": 0,
                         "lead_output": {"agent": "database-engineer",
                                         "output": "Confirmed hypothesis "
                                                   "H-001-STATESTORE by code review.",
                                         "tokens": {"total": 200},
                                         "latency_ms": 100}},
            hypotheses_injected=[HYP],
        )
        cands = _hyp_candidates(self.collector.generate_candidates([], src))
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["candidate_type"], "reinforce_hypothesis")
        self.assertEqual(cands[0]["target_memory"], HYP)
        self.assertEqual(cands[0]["outcome"], "observed")

    def test_18_shared_context_marker_set(self):
        src = _src(
            team_result={"status": "success", "completed_count": 1,
                         "failed_count": 0,
                         "lead_output": {"agent": "database-engineer",
                                         "output": "Confirmed hypothesis "
                                                   "H-001-STATESTORE by code review.",
                                         "tokens": {"total": 200},
                                         "latency_ms": 100}},
            hypotheses_injected=[HYP],
        )
        cand = _hyp_candidates(self.collector.generate_candidates([], src))[0]
        prov = cand["hypothesis_engagement"]
        self.assertTrue(prov["referenced"])
        self.assertTrue(prov["shared_context_with_other_agents"])
        self.assertEqual(cand["evidence"].get("is_lead"), True)

    def test_19_agent_not_referencing_abstains(self):
        src = _src(
            team_result={"status": "success", "completed_count": 1,
                         "failed_count": 0,
                         "lead_output": {"agent": "database-engineer",
                                         "output": "Just fixed the migration.",
                                         "tokens": {"total": 100},
                                         "latency_ms": 50}},
            hypotheses_injected=[HYP],
        )
        self.assertEqual(_hyp_candidates(self.collector.generate_candidates([], src)), [])

    def test_20_no_hypotheses_injected_absent(self):
        src = _src(
            team_result={"status": "success", "completed_count": 1,
                         "failed_count": 0,
                         "lead_output": {"agent": "database-engineer",
                                         "output": "Confirmed hypothesis "
                                                   "H-001-STATESTORE by code review.",
                                         "tokens": {"total": 200},
                                         "latency_ms": 100}},
        )
        self.assertEqual(_hyp_candidates(self.collector.generate_candidates([], src)), [])

    def test_21_team_refuted_weaken_hypothesis(self):
        src = _src(
            team_result={"status": "success", "completed_count": 1,
                         "failed_count": 0,
                         "lead_output": {"agent": "database-engineer",
                                         "output": "Hypothesis H-001-STATESTORE "
                                                   "was refuted by our tests.",
                                         "tokens": {"total": 200},
                                         "latency_ms": 100}},
            hypotheses_injected=[HYP],
        )
        cand = _hyp_candidates(self.collector.generate_candidates([], src))[0]
        self.assertEqual(cand["candidate_type"], "weaken_hypothesis")
        self.assertEqual(cand["outcome"], "refuted")


# ── D/E/F. Validator grouping, rejection, promotion safety ────────

def _cand(cid, mid, ctype, outcome, execution, session, qscore=4.0,
          output_hash="abcdef1234567890"):
    return {
        "candidate_id": cid,
        "target_memory": mid,
        "candidate_type": ctype,
        "outcome": outcome,
        "source_execution": execution,
        "quality_score": qscore,
        "evidence": {"session_id": session, "output_hash": output_hash},
    }


class TestValidator(unittest.TestCase):

    def test_22_rejects_weaken_hypothesis(self):
        cands = [_cand("C1", HYP, "weaken_hypothesis", "refuted",
                       "L1", "S1")]
        groups = validator.group_candidates_by_memory(cands)
        status, res = validator.validate_memory_group(HYP, groups[HYP])
        self.assertEqual(status, "rejected")
        self.assertIn("human review", res["rejection_reason"])

    def test_23_inconclusive_hyp_not_counted(self):
        cands = [_cand("C1", HYP, "reinforce_hypothesis", "inconclusive",
                       "L1", "S1")]
        groups = validator.group_candidates_by_memory(cands)
        self.assertEqual(groups[HYP]["executions"], set())

    def test_24_confirmed_counts_execution(self):
        cands = [_cand("C1", HYP, "reinforce_hypothesis", "confirmed",
                       "L1", "S1")]
        groups = validator.group_candidates_by_memory(cands)
        self.assertEqual(groups[HYP]["executions"], {"L1"})

    def test_25_1_obs_hypothesis_not_validated_not_promoted(self):
        cands = [_cand("C1", HYP, "reinforce_hypothesis", "confirmed",
                       "L1", "S1")]
        groups = validator.group_candidates_by_memory(cands)
        status, res = validator.validate_memory_group(HYP, groups[HYP])
        self.assertEqual(status, "hypothesis")
        self.assertEqual(res["validation_runs"], 1)

    def test_26_2_obs_validated(self):
        cands = [
            _cand("C1", HYP, "reinforce_hypothesis", "confirmed", "L1", "S1"),
            _cand("C2", HYP, "reinforce_hypothesis", "confirmed", "L2", "S2"),
        ]
        groups = validator.group_candidates_by_memory(cands)
        status, res = validator.validate_memory_group(HYP, groups[HYP])
        self.assertEqual(status, "validated")
        self.assertEqual(res["validation_runs"], 2)

    def test_27_mixed_inconclusive_confirmed_runs(self):
        cands = [
            _cand("C1", HYP, "reinforce_hypothesis", "inconclusive", "L1", "S1"),
            _cand("C2", HYP, "reinforce_hypothesis", "confirmed", "L2", "S2"),
        ]
        groups = validator.group_candidates_by_memory(cands)
        self.assertEqual(groups[HYP]["executions"], {"L2"})


if __name__ == "__main__":
    unittest.main()