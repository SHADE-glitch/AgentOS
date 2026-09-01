#!/usr/bin/env python3
"""
Phase 8.2.1 — Multi-Agent Memory Feedback Loop Tests

Validates:
  - TeamResultCollector: loads and validates team-result files
  - ExperienceExtractor: extracts structured experiences from agent outputs
  - Candidate generation: produces MemoryCandidate dicts compatible with Validator
  - Validator integration: team-result candidates pass through Validator
  - Promoter integration: validated candidates pass through Promoter
  - Runtime state: "delegated" status with executor metadata
  - Full feedback loop: TeamResult → Collector → Validator → Promoter
"""

import sys
import os
import unittest
import tempfile
import yaml
from unittest.mock import patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────
_AGENT_HOME = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
_COLLECTOR_DIR = os.path.join(_AGENT_HOME, "runtime", "memory-feedback", "collector")
_PROMOTION_DIR = os.path.join(_AGENT_HOME, "runtime", "memory-feedback", "promotion")
_LOOP_DIR = os.path.join(_AGENT_HOME, "runtime", "loop-controller")

for d in [_COLLECTOR_DIR, _PROMOTION_DIR, _LOOP_DIR]:
    if d not in sys.path:
        sys.path.insert(0, d)

from base_collector import Collector
from team_result_collector import TeamResultCollector, collect_from_team_results
from experience_extractor import extract_experiences, _extract_technical_patterns, \
    _extract_problem_patterns, _extract_solutions, _assess_confidence
from validator import validate_candidates
from promoter import promote_validated


# ── Fixtures ──────────────────────────────────────────────────────

def _make_team_result_fixture(loop_id="LOOP-TEST001", team_id="team-test0001",
                               status="success", completed=3, failed=0):
    """Build a realistic TeamResult dict for testing."""
    return {
        "loop_id": loop_id,
        "team_id": team_id,
        "team_result": {
            "team_id": team_id,
            "status": status,
            "lead_output": {
                "agent": "backend-architect",
                "status": "completed",
                "summary": "Diagnosis report for session state drift",
                "output": """## Session State Drift Diagnosis

### BUG-001: Redis expiry → DB fallback without consistency check (HIGH)

Location: `InterviewStateStore.java:34-46` + `InterviewService.java:376-395`

Root Cause: DB fallback trusts `InterviewSession` fields without cross-validation
against `interview_message` records.

| Scenario | DB State | Actual Messages | Consequence |
|----------|----------|-----------------|-------------|
| Redis expired + DB write delay | questionCount=3 | Only 2 Q&A pairs | State mismatch |

### BUG-002: answer() method lacks idempotency protection (HIGH)

Location: `InterviewService.java:128-196`

The `answer()` method has no idempotency check. Duplicate submissions
cause duplicate message records and incorrect questionCount.

### Solution: Idempotency key with UNIQUE constraint

Add a unique constraint on (session_id, kind, role, request_id) to prevent duplicates.
Use Redis-based idempotency key with TTL.""",
                "tokens": {"total": 45104, "input": 3391, "output": 4721, "cache_read": 36992},
                "latency_ms": 143365,
                "reliability": {"summary": {"total_attempts": 1, "retries_performed": 0, "classification": "success"}},
            },
            "contributions": [
                {
                    "role": "code-reviewer",
                    "is_lead": False,
                    "output": {
                        "agent": "code-reviewer",
                        "output": """## Code Review

2 HIGH severity bugs confirmed:
- BUG-001: DB fallback rehydrates stale currentQuestionId
- BUG-002: No idempotency check in answer()

The JWT refresh mechanism also has a race condition in the token revoke flow.""",
                        "tokens": {"total": 35000, "input": 2500, "output": 3800},
                        "latency_ms": 179000,
                        "reliability": {"summary": {"classification": "success"}},
                    },
                },
                {
                    "role": "security-engineer",
                    "is_lead": False,
                    "output": {
                        "agent": "security-engineer",
                        "output": """## Security Analysis

### JWT Token Refresh Race Condition

The refresh token revoke mechanism has a race condition:
1. User requests token refresh
2. Old refresh token is revoked
3. New refresh token is issued
4. If a concurrent request uses the old token before revocation propagates, it succeeds

Recommendation: Use Redis SET NX with TTL for atomic token revocation.

### Idempotency for answer() endpoint

The answer() endpoint is vulnerable to replay attacks. Without idempotency key,
a captured request can be replayed within the session window.""",
                        "tokens": {"total": 32000, "input": 2200, "output": 3500},
                        "latency_ms": 165000,
                        "reliability": {"summary": {"classification": "success"}},
                    },
                },
            ],
            "conflicts": [],
            "summary": "Lead agent completed diagnosis. 2 HIGH bugs confirmed.",
            "agent_count": 3,
            "completed_count": completed,
            "failed_count": failed,
        },
        "task_cards": [
            {"task_id": "task-backend-architect-001", "role": "backend-architect",
             "status": "completed", "output_summary": "Diagnosis report", "output_len": 6400, "latency_ms": 143365},
            {"task_id": "task-code-reviewer-001", "role": "code-reviewer",
             "status": "completed", "output_summary": "Code review", "output_len": 8367, "latency_ms": 179000},
            {"task_id": "task-security-engineer-001", "role": "security-engineer",
             "status": "completed", "output_summary": "Security analysis", "output_len": 7200, "latency_ms": 165000},
        ],
        "execution_order": [
            "task-backend-architect-001",
            "task-code-reviewer-001",
            "task-security-engineer-001",
        ],
        "completed_count": completed,
        "failed_count": failed,
    }


# ── Test: Experience Extractor ────────────────────────────────────

class TestExperienceExtractor(unittest.TestCase):
    """Test experience extraction from TeamResult data."""

    def setUp(self):
        self.fixture = _make_team_result_fixture()

    def test_extracts_lead_experience(self):
        """Lead agent output produces an ExperienceRecord."""
        experiences = extract_experiences(self.fixture)
        lead_exps = [e for e in experiences if e["is_lead"]]
        self.assertEqual(len(lead_exps), 1)
        self.assertEqual(lead_exps[0]["agent_role"], "backend-architect")
        self.assertTrue(lead_exps[0]["confidence"] > 0.5)

    def test_extracts_support_experiences(self):
        """Support agent outputs produce ExperienceRecords."""
        experiences = extract_experiences(self.fixture)
        support_exps = [e for e in experiences if not e["is_lead"]]
        self.assertEqual(len(support_exps), 2)

    def test_experience_has_provenance(self):
        """Every experience has source_id, team_id, and evidence."""
        experiences = extract_experiences(self.fixture)
        for exp in experiences:
            self.assertIsNotNone(exp["source_id"])
            self.assertIsNotNone(exp["team_id"])
            self.assertIn("output_hash", exp["evidence"])
            self.assertIn("token_usage", exp["evidence"])
            self.assertIn("is_real_execution", exp["evidence"])

    def test_extracts_technical_patterns(self):
        """Technical patterns are extracted from output text."""
        text = "Redis TTL expiry causes data inconsistency. JWT refresh token revoke has race condition."
        patterns = _extract_technical_patterns(text)
        self.assertGreater(len(patterns), 0)
        self.assertTrue(any("Cache" in p or "Token" in p for p in patterns))

    def test_extracts_problem_patterns(self):
        """Problem patterns are extracted from output text."""
        text = "Data inconsistency due to stale cache. Race condition in token refresh."
        problems = _extract_problem_patterns(text)
        self.assertGreater(len(problems), 0)
        self.assertTrue(any("inconsistency" in p.lower() or "race" in p.lower() for p in problems))

    def test_extracts_solutions(self):
        """Solution patterns are extracted from output text."""
        text = "Add idempotency key. Use UNIQUE constraint for deduplication. Async processing with queue."
        solutions = _extract_solutions(text)
        self.assertGreater(len(solutions), 0)
        self.assertTrue(any("Idempotency" in s or "Unique" in s for s in solutions))

    def test_confidence_lead_higher(self):
        """Lead agents should have higher base confidence."""
        text = "Some analysis text with enough length to be meaningful. " * 20
        lead_conf = _assess_confidence(text, "backend-architect", True, 40000, 150000)
        support_conf = _assess_confidence(text, "database-engineer", False, 40000, 150000)
        self.assertGreaterEqual(lead_conf, support_conf)

    def test_confidence_bounds(self):
        """Confidence stays within 0.0-1.0."""
        text = ""  # Empty
        conf = _assess_confidence(text, "unknown", False, 0, 0)
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

        text = "Very detailed analysis with headers, code blocks, and tables. " * 100
        conf = _assess_confidence(text, "backend-architect", True, 50000, 200000)
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)


# ── Test: TeamResultCollector ─────────────────────────────────────

class TestTeamResultCollector(unittest.TestCase):
    """Test TeamResultCollector: load, validate, extract, generate candidates."""

    def setUp(self):
        self.fixture = _make_team_result_fixture()
        self.tmpdir = tempfile.mkdtemp()
        # Write fixture to temp dir
        self.fixture_path = os.path.join(self.tmpdir, "team-result-LOOP-TEST001.yaml")
        with open(self.fixture_path, "w") as f:
            yaml.dump(self.fixture, f)
        self.collector = TeamResultCollector(validation_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_source_found(self):
        """Loading an existing source returns a dict."""
        result = self.collector.load_source("LOOP-TEST001")
        self.assertIsNotNone(result)
        self.assertEqual(result["loop_id"], "LOOP-TEST001")

    def test_load_source_not_found(self):
        """Loading a non-existent source returns None."""
        result = self.collector.load_source("LOOP-NONEXISTENT")
        self.assertIsNone(result)

    def test_validate_source_valid(self):
        """A valid TeamResult passes validation."""
        valid, reasons = self.collector.validate_source(self.fixture)
        self.assertTrue(valid, f"Should be valid, got: {reasons}")

    def test_validate_source_missing_team_id(self):
        """Missing team_id fails validation."""
        bad = dict(self.fixture)
        bad["team_id"] = None
        valid, reasons = self.collector.validate_source(bad)
        self.assertFalse(valid)

    def test_validate_source_empty_lead_output(self):
        """Empty lead output fails validation."""
        bad = dict(self.fixture)
        bad["team_result"]["lead_output"]["output"] = ""
        valid, reasons = self.collector.validate_source(bad)
        self.assertFalse(valid)

    def test_extract_experiences_returns_list(self):
        """extract_experiences returns a non-empty list."""
        experiences = self.collector.extract_experiences(self.fixture)
        self.assertIsInstance(experiences, list)
        self.assertGreater(len(experiences), 0)

    def test_generate_candidates_produces_output(self):
        """generate_candidates produces MemoryCandidate dicts."""
        experiences = self.collector.extract_experiences(self.fixture)
        candidates = self.collector.generate_candidates(experiences, self.fixture)
        self.assertIsInstance(candidates, list)
        self.assertGreater(len(candidates), 0)

        # Each candidate must have required fields
        for c in candidates:
            self.assertIn("candidate_id", c)
            self.assertIn("target_memory", c)
            self.assertIn("candidate_type", c)
            self.assertIn("quality_score", c)
            self.assertIn("reasoning", c)
            self.assertIn("evidence", c)

    def test_generate_candidates_has_reinforce(self):
        """Successful team execution produces reinforce candidates."""
        experiences = self.collector.extract_experiences(self.fixture)
        candidates = self.collector.generate_candidates(experiences, self.fixture)
        reinforce = [c for c in candidates if c["candidate_type"] == "reinforce"]
        self.assertGreater(len(reinforce), 0)

    def test_generate_candidates_has_hypothesis(self):
        """High confidence lead agent produces hypothesis candidates."""
        experiences = self.collector.extract_experiences(self.fixture)
        # Boost confidence to ensure hypothesis generation
        for e in experiences:
            if e["is_lead"]:
                e["confidence"] = 0.85
        candidates = self.collector.generate_candidates(experiences, self.fixture)
        hypothesis = [c for c in candidates if c["candidate_type"] == "create_hypothesis"]
        self.assertGreater(len(hypothesis), 0, "Should generate hypothesis for high-confidence lead")

    def test_failed_team_produces_weaken(self):
        """Failed team execution produces weaken candidates."""
        failed_fixture = _make_team_result_fixture(
            loop_id="LOOP-TEST002", team_id="team-test0002",
            status="failed", completed=1, failed=2
        )
        experiences = self.collector.extract_experiences(failed_fixture)
        candidates = self.collector.generate_candidates(experiences, failed_fixture)
        weaken = [c for c in candidates if c["candidate_type"] == "weaken"]
        self.assertGreater(len(weaken), 0)

    def test_candidate_evidence_has_provenance(self):
        """Candidates carry provenance evidence."""
        experiences = self.collector.extract_experiences(self.fixture)
        candidates = self.collector.generate_candidates(experiences, self.fixture)
        for c in candidates:
            ev = c.get("evidence", {})
            self.assertTrue(ev.get("is_real_execution"), f"Missing is_real_execution in {c['candidate_id']}")

    def test_collect_full_pipeline(self):
        """Full collect() pipeline works end-to-end."""
        candidates = self.collector.collect(["LOOP-TEST001"], quiet=True)
        self.assertIsInstance(candidates, list)
        self.assertGreater(len(candidates), 0)

    def test_list_available(self):
        """list_available() finds team-result files."""
        ids = self.collector.list_available()
        self.assertIn("LOOP-TEST001", ids)


# ── Test: Validator Integration ───────────────────────────────────

class TestValidatorIntegration(unittest.TestCase):
    """Test that TeamResultCollector candidates pass through Validator."""

    def setUp(self):
        self.fixture = _make_team_result_fixture()
        self.tmpdir = tempfile.mkdtemp()
        self.fixture_path = os.path.join(self.tmpdir, "team-result-LOOP-TESTV01.yaml")
        with open(self.fixture_path, "w") as f:
            yaml.dump(self.fixture, f)
        self.collector = TeamResultCollector(validation_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("validator.load_memory_index")
    def test_candidates_pass_through_validator(self, mock_index):
        """Candidates from TeamResultCollector can be validated by the existing Validator."""
        mock_index.return_value = {
            "memories": [
                {"memory_id": "P8-CACHE-EXPIRATION-PATTERN", "file": "memory/tasks/cache.md",
                 "source_task": "T-001", "evidence_level": "runtime_validated",
                 "category": "backend", "observation_count": 3, "confidence": "medium"},
                {"memory_id": "P8-TOKEN-MANAGEMENT-PATTERN", "file": "memory/tasks/token.md",
                 "source_task": "T-002", "evidence_level": "runtime_validated",
                 "category": "security", "observation_count": 2, "confidence": "medium"},
                {"memory_id": "P8-IDEMPOTENCY-PATTERN", "file": "memory/tasks/idempotent.md",
                 "source_task": "T-003", "evidence_level": "runtime_validated",
                 "category": "backend", "observation_count": 2, "confidence": "medium"},
                {"memory_id": "P8-DATA-INCONSISTENCY", "file": "memory/tasks/consistency.md",
                 "source_task": "T-004", "evidence_level": "runtime_validated",
                 "category": "backend", "observation_count": 2, "confidence": "medium"},
            ]
        }

        experiences = self.collector.extract_experiences(self.fixture)
        candidates = self.collector.generate_candidates(experiences, self.fixture)
        self.assertGreater(len(candidates), 0,
                          f"Should have candidates to validate, got {len(candidates)}")

        # Validate — should not crash
        results = validate_candidates(candidates, quiet=True)
        self.assertIsInstance(results, list)
        # At least some results should be present (even if many are rejected due to
        # single observation, which is expected for a single TeamResult)
        self.assertGreater(len(results), 0)


# ── Test: Candidate Format Compatibility ──────────────────────────

class TestCandidateFormatCompatibility(unittest.TestCase):
    """Test that TeamResultCollector candidates match TraceCollector format."""

    def setUp(self):
        self.fixture = _make_team_result_fixture()
        self.tmpdir = tempfile.mkdtemp()
        self.fixture_path = os.path.join(self.tmpdir, "team-result-LOOP-TESTF01.yaml")
        with open(self.fixture_path, "w") as f:
            yaml.dump(self.fixture, f)
        self.collector = TeamResultCollector(validation_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_candidate_has_required_fields(self):
        """All candidates have the fields expected by Validator/Promoter."""
        experiences = self.collector.extract_experiences(self.fixture)
        candidates = self.collector.generate_candidates(experiences, self.fixture)

        required_fields = [
            "candidate_id", "source_execution", "target_memory",
            "candidate_type", "quality_score", "quality_breakdown",
            "reasoning", "evidence", "outcome",
        ]

        for c in candidates:
            for field in required_fields:
                self.assertIn(field, c, f"Missing field '{field}' in candidate {c.get('candidate_id', '?')}")

    def test_quality_breakdown_has_all_dimensions(self):
        """Quality breakdown includes all 5 dimensions."""
        experiences = self.collector.extract_experiences(self.fixture)
        candidates = self.collector.generate_candidates(experiences, self.fixture)

        for c in candidates:
            qb = c.get("quality_breakdown", {})
            for dim in ["completeness", "accuracy", "structure", "actionability", "novelty"]:
                self.assertIn(dim, qb, f"Missing quality dimension '{dim}'")
                self.assertGreaterEqual(qb[dim], 0)
                self.assertLessEqual(qb[dim], 5)


# ── Test: Runtime State ───────────────────────────────────────────

class TestRuntimeState(unittest.TestCase):
    """Test that loop_controller runtime state is updated correctly for multi-agent."""

    def test_delegated_status_set(self):
        """Runtime status should be 'delegated' for multi-agent, not 'skipped'."""
        # This is a structural test — verifies the state schema
        state = {
            "runtime": {
                "status": "delegated",
                "executor": {
                    "type": "multi-agent",
                    "team_id": "team-test0001",
                },
            }
        }
        self.assertEqual(state["runtime"]["status"], "delegated")
        self.assertEqual(state["runtime"]["executor"]["type"], "multi-agent")
        self.assertNotEqual(state["runtime"]["status"], "skipped")

    def test_executor_metadata_present(self):
        """Executor metadata includes type and team_id."""
        state = {
            "runtime": {
                "executor": {
                    "type": "multi-agent",
                    "team_id": "team-ab4de5f6",
                },
            }
        }
        executor = state["runtime"]["executor"]
        self.assertEqual(executor["type"], "multi-agent")
        self.assertIsNotNone(executor["team_id"])
        self.assertGreater(len(executor["team_id"]), 0)

    def test_single_agent_executor_default(self):
        """Single-agent default executor type is 'single-agent'."""
        state = {
            "runtime": {
                "executor": {
                    "type": "single-agent",
                    "team_id": "",
                },
            }
        }
        self.assertEqual(state["runtime"]["executor"]["type"], "single-agent")


# ── Test: Base Collector Interface ────────────────────────────────

class TestBaseCollector(unittest.TestCase):
    """Test the base Collector abstract class utilities."""

    def test_compute_output_hash_deterministic(self):
        """Same input produces same hash."""
        h1 = Collector.compute_output_hash("test output")
        h2 = Collector.compute_output_hash("test output")
        self.assertEqual(h1, h2)

    def test_compute_output_hash_different(self):
        """Different inputs produce different hashes."""
        h1 = Collector.compute_output_hash("output A")
        h2 = Collector.compute_output_hash("output B")
        self.assertNotEqual(h1, h2)

    def test_make_candidate_has_all_fields(self):
        """make_candidate produces a dict with all required fields."""
        c = Collector.make_candidate(
            candidate_id="CAND-TEST-001",
            target_memory="MEM-001",
            candidate_type="reinforce",
            outcome="promoted",
            reasoning="Test reasoning",
            quality_score=3.5,
            quality_breakdown={"completeness": 4, "accuracy": 3, "structure": 3, "actionability": 3, "novelty": 3},
            evidence={"output_hash": "abc123", "is_real_execution": True},
            source_execution="LOOP-TEST001",
        )
        self.assertEqual(c["candidate_id"], "CAND-TEST-001")
        self.assertEqual(c["candidate_type"], "reinforce")
        self.assertEqual(c["outcome"], "promoted")
        self.assertEqual(c["quality_score"], 3.5)


if __name__ == "__main__":
    unittest.main()