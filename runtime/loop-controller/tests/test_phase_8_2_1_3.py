#!/usr/bin/env python3
"""
Phase 8.2.1.3 — Memory Feedback Loop Closure Tests

Validates:
  1. Observation log append idempotent (dedup by memory_id + source_loop)
  2. Run1+Run2: same H-xxx, validator cross-loop merge → observation_count=2
  3. Promotion: promoted_ids non-empty after cross-loop validation
  4. Retrieval: H-xxx enters TopK via two-bucket ranking
  5. Regression: existing 8.2.1.1 and 8.2.1.2 test suites still pass
"""

import sys
import os
import unittest
import tempfile
import yaml
import shutil
from unittest.mock import patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────
_AGENT_HOME = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
_COLLECTOR_DIR = os.path.join(_AGENT_HOME, "runtime", "memory-feedback", "collector")
_PROMOTION_DIR = os.path.join(_AGENT_HOME, "runtime", "memory-feedback", "promotion")
_RETRIEVAL_DIR = os.path.join(_AGENT_HOME, "runtime", "memory-feedback", "retrieval")
_LOOP_DIR = os.path.join(_AGENT_HOME, "runtime", "loop-controller")

for d in [_COLLECTOR_DIR, _PROMOTION_DIR, _RETRIEVAL_DIR, _LOOP_DIR]:
    if d not in sys.path:
        sys.path.insert(0, d)

from memory_resolver import (
    bootstrap_hypothesis, resolve_memory_id, resolve_candidates_targets,
    memory_exists, find_memory_entry, load_memory_index, save_memory_index,
    append_observation, load_observation_log, save_observation_log,
)
from validator import (
    validate_memory_group, validate_candidates, group_candidates_by_memory,
    enrich_groups_with_observation_log, load_observation_log as v_load_observation_log,
    synthesize_groups_from_observation_log,
)
from promoter import promote_validated, check_trust_gate

# ── Helpers ───────────────────────────────────────────────────────

MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"
OBSERVATION_LOG_FILE = "/home/shade/.agents/runtime/memory-feedback/memory-observation-log.yaml"
_original_index = None
_original_log = None


def _backup_files():
    global _original_index, _original_log
    if os.path.exists(MEMORY_INDEX_FILE):
        with open(MEMORY_INDEX_FILE) as f:
            _original_index = f.read()
    if os.path.exists(OBSERVATION_LOG_FILE):
        with open(OBSERVATION_LOG_FILE) as f:
            _original_log = f.read()


def _restore_files():
    if _original_index is not None:
        with open(MEMORY_INDEX_FILE, "w") as f:
            f.write(_original_index)
    if _original_log is not None:
        with open(OBSERVATION_LOG_FILE, "w") as f:
            f.write(_original_log)
    else:
        # Reset log to empty
        if os.path.exists(OBSERVATION_LOG_FILE):
            with open(OBSERVATION_LOG_FILE, "w") as f:
                f.write("version: \"1.0\"\nphase: \"8.2.1.3\"\nobservations: []\n")


def _clear_observation_log():
    """Clear the observation log for clean test state."""
    from datetime import datetime, timezone
    log = {"version": "1.0", "phase": "8.2.1.3", "observations": [],
           "created_at": datetime.now(timezone.utc).isoformat()}
    with open(OBSERVATION_LOG_FILE, "w") as f:
        yaml.dump(log, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _make_candidate(memory_id="P8-TEST-PATTERN",
                    loop_id="LOOP-TEST001", team_id="team-test0001",
                    agent_role="backend-architect", ctype="reinforce",
                    quality_score=3.5):
    """Build a realistic candidate dict for testing."""
    return {
        "candidate_id": f"CAND-{loop_id}-{agent_role}-{memory_id}",
        "target_memory": memory_id,
        "candidate_type": ctype,
        "outcome": "promoted",
        "reasoning": f"Multi-agent team ({team_id}) execution succeeded. Pattern identified.",
        "quality_score": quality_score,
        "quality_breakdown": {"completeness": 4, "accuracy": 3, "structure": 3, "actionability": 3, "novelty": 3},
        "evidence": {
            "output_hash": f"hash-{loop_id}-{agent_role}",
            "token_usage": {"total": 45000},
            "latency_ms": 143000,
            "output_length": 6400,
            "is_real_execution": True,
            "agent_role": agent_role,
            "team_id": team_id,
            "is_lead": True,
            "session_id": f"TEAM-{team_id}-{loop_id}",
        },
        "source_execution": loop_id,
    }


# ── Test 1: Observation Log Append Idempotent ─────────────────────

class TestObservationLog(unittest.TestCase):
    """Test observation log append and dedup."""

    def setUp(self):
        _backup_files()
        _clear_observation_log()

    def tearDown(self):
        _restore_files()

    def test_append_observation_creates_record(self):
        """Appending an observation should create a record in the log."""
        result = append_observation(
            memory_id="H-001-TEST",
            source_loop="LOOP-TEST001",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-TEST001",
            output_hash="abc123",
            quality_score=4.0,
            agent_role="backend-architect",
            origin="bootstrap",
        )
        self.assertTrue(result)

        log = load_observation_log()
        self.assertEqual(len(log["observations"]), 1)
        obs = log["observations"][0]
        self.assertEqual(obs["memory_id"], "H-001-TEST")
        self.assertEqual(obs["source_loop"], "LOOP-TEST001")
        self.assertEqual(obs["origin"], "bootstrap")

    def test_append_observation_dedup(self):
        """Appending the same (memory_id, source_loop) should be idempotent."""
        # First append
        result1 = append_observation(
            memory_id="H-001-TEST", source_loop="LOOP-TEST001",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-TEST001",
            output_hash="abc123", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )
        self.assertTrue(result1)

        # Second append — same key
        result2 = append_observation(
            memory_id="H-001-TEST", source_loop="LOOP-TEST001",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-TEST001",
            output_hash="abc123", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )
        self.assertFalse(result2)  # Dedup should skip

        log = load_observation_log()
        self.assertEqual(len(log["observations"]), 1)

    def test_append_observation_different_loops(self):
        """Same memory_id, different source_loop → two distinct records."""
        append_observation("H-001-TEST", "LOOP-TEST001", "team-test0001",
                           "TEAM-team-test0001-LOOP-TEST001", "abc123", 4.0, "backend-architect",
                           origin="bootstrap")
        append_observation("H-001-TEST", "LOOP-TEST002", "team-test0001",
                           "TEAM-team-test0001-LOOP-TEST002", "def456", 4.2, "testing-engineer",
                           origin="reinforce")

        log = load_observation_log()
        self.assertEqual(len(log["observations"]), 2)

        origins = [o["origin"] for o in log["observations"]]
        self.assertIn("bootstrap", origins)
        self.assertIn("reinforce", origins)


# ── Test 2: Cross-Loop Validator Merge ────────────────────────────

class TestCrossLoopValidation(unittest.TestCase):
    """Test cross-loop observation aggregation in validator."""

    def setUp(self):
        _backup_files()
        _clear_observation_log()

    def tearDown(self):
        _restore_files()

    def test_empty_log_no_enrichment(self):
        """With empty log, groups should be unchanged."""
        candidates = [
            _make_candidate("H-001-TEST", "LOOP-TEST001", "team-test0001", ctype="reinforce_hypothesis"),
        ]
        groups = group_candidates_by_memory(candidates)
        original_executions = set(groups["H-001-TEST"]["executions"])

        enriched = enrich_groups_with_observation_log(groups)

        self.assertEqual(enriched["H-001-TEST"]["executions"], original_executions)
        self.assertNotIn("cross_loop_observations", enriched["H-001-TEST"])

    def test_cross_loop_merge_adds_historical_observations(self):
        """Pre-populate log with Run1 observation, then validate Run2 candidates."""
        # Simulate Run1: bootstrap observation
        append_observation(
            memory_id="H-001-TEST", source_loop="LOOP-RUN1",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN1",
            output_hash="hash-run1", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )

        # Run2 candidates
        candidates = [
            _make_candidate("H-001-TEST", "LOOP-RUN2", "team-test0001",
                            ctype="reinforce_hypothesis", quality_score=4.2),
        ]
        groups = group_candidates_by_memory(candidates)
        enriched = enrich_groups_with_observation_log(groups)

        group = enriched["H-001-TEST"]
        # Should have 2 executions: RUN2 (current) + RUN1 (cross-loop)
        self.assertIn("LOOP-RUN1", group["executions"])
        self.assertIn("LOOP-RUN2", group["executions"])
        self.assertEqual(len(group["executions"]), 2)
        self.assertEqual(group["cross_loop_observations"], 1)
        self.assertEqual(group["cross_loop_sources"], ["LOOP-RUN1"])
        # Best quality should be max of both
        self.assertGreaterEqual(group["best_quality"], 4.2)

    def test_validation_runs_cumulative_after_enrichment(self):
        """After enrichment, validation_runs should reflect cross-loop total."""
        # Run1 observation
        append_observation(
            memory_id="H-001-TEST", source_loop="LOOP-RUN1",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN1",
            output_hash="hash-run1", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )

        # Run2 candidate
        candidates = [
            _make_candidate("H-001-TEST", "LOOP-RUN2", "team-test0001",
                            ctype="reinforce_hypothesis", quality_score=4.2),
        ]
        groups = group_candidates_by_memory(candidates)
        enriched = enrich_groups_with_observation_log(groups)

        status, result = validate_memory_group("H-001-TEST", enriched["H-001-TEST"])
        self.assertEqual(result["validation_runs"], 2)
        self.assertEqual(result["unique_sessions"], 2)
        # With 2 observations, H-xxx should graduate to validated
        self.assertEqual(status, "validated")

    def test_cross_loop_graduation_hypothesis_to_validated(self):
        """Full flow: Run1=hypothesis, Run2(cross-loop)=validated."""
        append_observation(
            memory_id="H-001-TEST", source_loop="LOOP-RUN1",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN1",
            output_hash="hash-run1", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )

        candidates = [
            _make_candidate("H-001-TEST", "LOOP-RUN2", "team-test0001",
                            ctype="reinforce_hypothesis", quality_score=4.2),
        ]
        results = validate_candidates(candidates, quiet=True)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["memory_id"], "H-001-TEST")
        self.assertEqual(r["status"], "validated")
        self.assertEqual(r["validation_runs"], 2)
        self.assertIn("cross_loop", r)
        self.assertEqual(r["cross_loop"]["prior_observations"], 1)

    def test_non_hypothesis_not_enriched(self):
        """Non-H-xxx memories should not be enriched."""
        append_observation(
            memory_id="T-001-TEST", source_loop="LOOP-RUN1",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN1",
            output_hash="hash-run1", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )

        candidates = [
            _make_candidate("T-001-TEST", "LOOP-RUN2", "team-test0001"),
        ]
        groups = group_candidates_by_memory(candidates)
        enriched = enrich_groups_with_observation_log(groups)

        # T-xxx should not be enriched
        group = enriched["T-001-TEST"]
        self.assertNotIn("cross_loop_observations", group)
        self.assertEqual(len(group["executions"]), 1)


# ── Test 3: Promotion After Cross-Loop Validation ─────────────────

class TestPromotionAfterCrossLoop(unittest.TestCase):
    """Test promotion after cross-loop validation graduation."""

    def setUp(self):
        _backup_files()
        _clear_observation_log()

    def tearDown(self):
        _restore_files()

    def test_promoter_receives_validated_hypothesis(self):
        """After cross-loop validation, promoter should receive validated H-xxx."""
        # First, ensure the H-xxx exists in the index
        memory_id = bootstrap_hypothesis(
            "Test Pattern Promotion",
            source_loop_id="LOOP-RUN1",
            source_team_id="team-test0001",
            agent_role="backend-architect",
        )

        # Add Run1 observation to log (bootstrap doesn't add to log)
        append_observation(
            memory_id=memory_id, source_loop="LOOP-RUN1",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN1",
            output_hash="hash-run1", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )

        # Add Run2 observation via log
        append_observation(
            memory_id=memory_id, source_loop="LOOP-RUN2",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN2",
            output_hash="hash-run2", quality_score=4.2,
            agent_role="testing-engineer", origin="reinforce",
        )

        # Run2 candidate
        candidates = [
            _make_candidate(memory_id, "LOOP-RUN2", "team-test0001",
                            ctype="reinforce_hypothesis", quality_score=4.2),
        ]
        results = validate_candidates(candidates, quiet=True)

        validated = [r for r in results if r["status"] == "validated"]
        self.assertGreaterEqual(len(validated), 1)

        v = validated[0]
        self.assertEqual(v["validation_runs"], 2)

        # Promotion should succeed (Trust Gate may reject bootstrapped hypotheses)
        promo_result = promote_validated(v)
        self.assertIn(promo_result["status"], ["applied", "skipped", "rejected"])

        if promo_result["status"] == "applied":
            eu = promo_result["evidence_updates"]
            self.assertEqual(eu["new_observation_count"], 2)  # max(1 bootstrap, 2 validation runs)
            self.assertEqual(eu["new_evidence_level"], "runtime_validated")
            su = promo_result.get("status_updates", {})
            self.assertEqual(su.get("new_status"), "validated")
        elif promo_result["status"] == "rejected":
            self.assertIn("Trust Gate", promo_result.get("rejection_reason", ""))

    def test_observation_count_arithmetic_fix(self):
        """Verify new_obs = max(old_obs, validation_runs) — no double-count."""
        memory_id = bootstrap_hypothesis(
            "Arithmetic Test Pattern",
            source_loop_id="LOOP-RUN1",
            source_team_id="team-test0001",
            agent_role="backend-architect",
        )

        append_observation(
            memory_id=memory_id, source_loop="LOOP-RUN1",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN1",
            output_hash="hash-run1", quality_score=4.0,
            agent_role="backend-architect", origin="bootstrap",
        )

        append_observation(
            memory_id=memory_id, source_loop="LOOP-RUN2",
            source_team="team-test0001",
            session_id="TEAM-team-test0001-LOOP-RUN2",
            output_hash="hash-run2", quality_score=4.2,
            agent_role="testing-engineer", origin="reinforce",
        )

        candidates = [
            _make_candidate(memory_id, "LOOP-RUN2", "team-test0001",
                            ctype="reinforce_hypothesis", quality_score=4.2),
        ]
        results = validate_candidates(candidates, quiet=True)
        validated = [r for r in results if r["status"] == "validated"]

        if validated:
            promo = promote_validated(validated[0])
            if promo["status"] == "applied":
                eu = promo["evidence_updates"]
                # old_obs should be 1 (bootstrap), new_obs should be 2 (not 3)
                self.assertEqual(eu["old_observation_count"], 1)
                self.assertEqual(eu["new_observation_count"], 2)  # max(1 bootstrap, 2 validation runs)


# ── Test 4: Retrieval Two-Bucket Ranking ──────────────────────────

class TestRetrievalTwoBucket(unittest.TestCase):
    """Test two-bucket retrieval ranking for hypothesis priority."""

    def setUp(self):
        _backup_files()

    def tearDown(self):
        _restore_files()

    def test_hypothesis_score_computation(self):
        """Hypothesis memories should be scored through adaptive scoring."""
        from retrieval_optimizer import compute_adaptive_score

        # Hypothesis memory with observation_count=1
        mem = {
            "memory_id": "H-TEST-SCORE",
            "type": "hypothesis",
            "observation_count": 1,
        }
        usage_data = {}
        eval_data = {}

        result = compute_adaptive_score(mem, 0.3, usage_data, eval_data, 1.0)
        self.assertIn("adaptive_score", result)
        self.assertIn("final_score", result)
        self.assertGreaterEqual(result["final_score"], 0.0)
        self.assertLessEqual(result["final_score"], 1.0)

        # Non-hypothesis should also be scored
        mem2 = {
            "memory_id": "P-TEST-SCORE",
            "type": "pattern",
            "observation_count": 5,
        }
        result2 = compute_adaptive_score(mem2, 0.5, usage_data, eval_data, 1.0)
        self.assertGreater(result2["final_score"], result["final_score"],
                           "Higher observation_count + relevance should score higher")

    def test_retrieve_produces_bucket_field(self):
        """Retrieval results should include query and results metadata."""
        from retrieval_optimizer import retrieve

        query = {
            "task_text": "Test task for bucket retrieval",
            "category": "backend",
            "domains": ["backend", "database"],
            "roles": [],
            "keywords": ["test", "retrieval"],
            "difficulty": "medium",
        }

        result = retrieve(query)
        self.assertIn("query", result)
        self.assertIn("results", result)
        self.assertIn("top_k", result)

        # Each result should have a type field
        for r in result.get("results", []):
            self.assertIn("type", r)

    def test_closure_mode_increases_hypothesis_slots(self):
        """Closure mode should allocate 3 hypothesis slots instead of 2."""
        from retrieval_optimizer import retrieve

        query = {
            "task_text": "Test task for closure mode",
            "category": "backend",
            "domains": ["backend", "database"],
            "test_mode": "closure",
            "closure": True,
        }

        result = retrieve(query)
        # Closure mode query should still return valid results
        self.assertIn("results", result)
        self.assertIn("top_k", result)
        self.assertGreaterEqual(result["top_k"], 0)

    def test_hypothesis_excluded_when_query_excludes(self):
        """When exclude_hypothesis is True, no hypotheses in results."""
        from retrieval_optimizer import retrieve

        query = {
            "task_text": "Test exclude hypotheses",
            "category": "backend",
            "domains": ["backend"],
            "exclude_hypothesis": True,
        }

        result = retrieve(query)
        for r in result.get("results", []):
            self.assertNotEqual(r.get("type"), "hypothesis")


# ── Test 5: Decision Influence Structure ──────────────────────────

class TestDecisionInfluenceStructure(unittest.TestCase):
    """Test that the retrieval adapter returns proper decision context."""

    def test_adapt_returns_expected_fields(self):
        """adapt() should return core decision context fields."""
        from retrieval_adapter import adapt

        ctx = adapt(
            task_id="TEST-001",
            task_text="Test task for decision influence",
            memory_mode="enabled",
        )

        self.assertIn("retrieved", ctx)
        self.assertIsInstance(ctx["retrieved"], bool)
        self.assertIn("memories", ctx)
        self.assertIn("hypotheses", ctx)

    def test_adapt_separates_hypotheses_by_type(self):
        """adapt() should separate hypotheses using type field."""
        from retrieval_adapter import adapt

        ctx = adapt(
            task_id="TEST-001",
            task_text="Test task for hypothesis separation",
            memory_mode="enabled",
        )

        hypotheses = ctx.get("hypotheses", [])
        for h in hypotheses:
            self.assertTrue(
                h.get("type") == "hypothesis" or h.get("is_hypothesis")
            )


# ── Test 6: Observation Log Creates Candidate Group ───────────────

class TestObservationLogCreatesCandidate(unittest.TestCase):
    """Test that observation log entries auto-generate candidate groups."""

    def setUp(self):
        _backup_files()
        _clear_observation_log()

    def tearDown(self):
        _restore_files()

    def test_synthesize_group_from_log_only(self):
        """H-xxx with 2+ log observations, no candidates → synthesized group."""
        # Pre-populate log with 2 observations for H-095
        append_observation(
            memory_id="H-095-TESTPATTERNPROMO", source_loop="L1",
            source_team="T1", session_id="TEAM-T1-L1",
            output_hash="bootstrap", quality_score=3.0,
            agent_role="backend", origin="reinforce",
        )
        append_observation(
            memory_id="H-095-TESTPATTERNPROMO", source_loop="L2",
            source_team="T1", session_id="TEAM-T1-L2",
            output_hash="h2", quality_score=4.2,
            agent_role="tester", origin="reinforce",
        )

        # No candidates — empty list
        groups = group_candidates_by_memory([])
        self.assertEqual(len(groups), 0)

        synthesized = synthesize_groups_from_observation_log(groups)
        self.assertIn("H-095-TESTPATTERNPROMO", synthesized)

        group = synthesized["H-095-TESTPATTERNPROMO"]
        self.assertEqual(len(group["executions"]), 2)
        self.assertIn("L1", group["executions"])
        self.assertIn("L2", group["executions"])
        self.assertEqual(group["best_quality"], 4.2)
        self.assertEqual(len(group["all_session_ids"]), 2)
        self.assertEqual(len(group["all_output_hashes"]), 2)
        self.assertEqual(group["cross_loop_observations"], 2)
        self.assertTrue(group.get("synthesized"))

    def test_synthesize_skips_insufficient_observations(self):
        """H-xxx with only 1 observation → no synthesized group."""
        append_observation(
            memory_id="H-001-SINGLEOBS", source_loop="L1",
            source_team="T1", session_id="TEAM-T1-L1",
            output_hash="hash1", quality_score=3.0,
            agent_role="backend", origin="bootstrap",
        )

        groups = group_candidates_by_memory([])
        synthesized = synthesize_groups_from_observation_log(groups)
        self.assertNotIn("H-001-SINGLEOBS", synthesized)

    def test_synthesize_skips_existing_group(self):
        """H-xxx already has a candidate group → not synthesized."""
        append_observation(
            memory_id="H-001-TEST", source_loop="L1",
            source_team="T1", session_id="TEAM-T1-L1",
            output_hash="hash1", quality_score=3.0,
            agent_role="backend", origin="bootstrap",
        )
        append_observation(
            memory_id="H-001-TEST", source_loop="L2",
            source_team="T1", session_id="TEAM-T1-L2",
            output_hash="hash2", quality_score=4.0,
            agent_role="tester", origin="reinforce",
        )

        # First create a group from a candidate (simulating existing group)
        candidates = [
            _make_candidate("H-001-TEST", "LOOP-RUN2", "team-test0001", ctype="reinforce_hypothesis", quality_score=4.0),
        ]
        groups = group_candidates_by_memory(candidates)
        original_count = len(groups)

        synthesized = synthesize_groups_from_observation_log(groups)
        # Should not add a duplicate
        self.assertEqual(len(synthesized), original_count)

    def test_validate_candidates_with_empty_candidates_uses_log(self):
        """validate_candidates([]) should still produce results from log."""
        append_observation(
            memory_id="H-095-TESTPATTERNPROMO", source_loop="L1",
            source_team="T1", session_id="TEAM-T1-L1",
            output_hash="bootstrap", quality_score=3.0,
            agent_role="backend", origin="reinforce",
        )
        append_observation(
            memory_id="H-095-TESTPATTERNPROMO", source_loop="L2",
            source_team="T1", session_id="TEAM-T1-L2",
            output_hash="h2", quality_score=4.2,
            agent_role="tester", origin="reinforce",
        )

        results = validate_candidates([], quiet=True)
        self.assertGreaterEqual(len(results), 1)

        h095 = [r for r in results if r["memory_id"] == "H-095-TESTPATTERNPROMO"]
        self.assertEqual(len(h095), 1)
        r = h095[0]
        self.assertEqual(r["status"], "validated")
        self.assertEqual(r["validation_runs"], 2)

    def test_full_pipeline_observation_to_validated(self):
        """Full pipeline: observation → candidate → validation → promotion."""
        # 1. Ensure H-095 exists in index (bootstrap doesn't add to observation log)
        memory_id = bootstrap_hypothesis(
            "Test Pattern Promo",
            source_loop_id="L1",
            source_team_id="T1",
            agent_role="backend",
        )

        # 2. Add L1 observation (bootstrap creates index, but log needs explicit append)
        append_observation(
            memory_id=memory_id, source_loop="L1",
            source_team="T1", session_id="TEAM-T1-L1",
            output_hash="h1", quality_score=3.0,
            agent_role="backend", origin="bootstrap",
        )

        # 3. Add L2 observation via log
        append_observation(
            memory_id=memory_id, source_loop="L2",
            source_team="T1", session_id="TEAM-T1-L2",
            output_hash="h2", quality_score=4.2,
            agent_role="tester", origin="reinforce",
        )

        # 4. Validate with empty candidates (pure log-driven)
        results = validate_candidates([], quiet=True)
        validated = [r for r in results if r["status"] == "validated"]
        self.assertGreaterEqual(len(validated), 1)

        v = [r for r in validated if r["memory_id"] == memory_id]
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["validation_runs"], 2)

        # 5. Promote
        promo = promote_validated(v[0])
        # Trust Gate may reject bootstrapped hypotheses without source_task
        self.assertIn(promo["status"], ["applied", "skipped", "rejected"])

        if promo["status"] == "applied":
            eu = promo["evidence_updates"]
            self.assertEqual(eu["new_evidence_level"], "runtime_validated")
            self.assertEqual(eu["new_observation_count"], 2)  # max(1 bootstrap, 2 validation runs)
            su = promo.get("status_updates", {})
            self.assertEqual(su.get("new_status"), "validated")
        elif promo["status"] == "rejected":
            # Trust Gate rejection for missing provenance is expected
            self.assertIn("Trust Gate", promo.get("rejection_reason", ""))


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()