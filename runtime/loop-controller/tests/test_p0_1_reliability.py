#!/usr/bin/env python3
"""
Regression Tests — P0-1: Execution Reliability Guard

Tests:
  1. TIMEOUT classification and retry logic
  2. RETRY_STORM detection
  3. ORCHESTRATION_FAILURE vs REAL_AGENT_FAILURE distinction
  4. Model fallback chain
  5. Early termination
  6. Backoff calculation

These tests verify the Agent OS reliability guard works correctly
without needing to actually invoke the runtime provider.
"""

import sys
import os
import unittest

# Add loop-controller to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from execution_reliability import (
    FailureType,
    FailureCategory,
    FailureRecord,
    ReliabilityConfig,
    classify_failure,
    should_retry,
    compute_backoff,
    get_fallback_model,
    create_default_config,
    ReliabilitySummary,
)


class TestFailureClassification(unittest.TestCase):
    """Test that failures are correctly classified."""

    def setUp(self):
        self.config = create_default_config()

    def test_timeout_classification(self):
        """TIMEOUT → REAL_AGENT_FAILURE"""
        result = {
            "status": "timeout",
            "error": "opencode run exceeded 300s timeout",
            "latency_ms": 300000,
            "provider": "opencode",
            "model": "test-model",
            "response_text": "",
        }
        failure = classify_failure(result, 1, 300000, self.config)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_type, FailureType.TIMEOUT)
        self.assertEqual(failure.category, FailureCategory.REAL_AGENT_FAILURE)

    def test_no_output_classification(self):
        """NO_OUTPUT → REAL_AGENT_FAILURE"""
        result = {
            "status": "error",
            "error": "No text response in OpenCode output",
            "latency_ms": 5000,
            "provider": "opencode",
            "model": "test-model",
            "response_text": "",
        }
        failure = classify_failure(result, 1, 5000, self.config)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_type, FailureType.NO_OUTPUT)
        self.assertEqual(failure.category, FailureCategory.REAL_AGENT_FAILURE)

    def test_model_failure_classification(self):
        """MODEL_FAILURE → REAL_AGENT_FAILURE"""
        result = {
            "status": "error",
            "error": "opencode exit code 1: some error",
            "latency_ms": 1000,
            "provider": "opencode",
            "model": "test-model",
            "response_text": "",
        }
        failure = classify_failure(result, 1, 1000, self.config)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_type, FailureType.MODEL_FAILURE)
        self.assertEqual(failure.category, FailureCategory.REAL_AGENT_FAILURE)

    def test_provider_error_classification(self):
        """PROVIDER_ERROR → ORCHESTRATION_FAILURE"""
        result = {
            "status": "error",
            "error": "Unknown provider: bad-provider",
            "latency_ms": 0,
            "provider": "bad-provider",
            "model": "test-model",
            "response_text": "",
        }
        failure = classify_failure(result, 1, 0, self.config)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_type, FailureType.PROVIDER_ERROR)
        self.assertEqual(failure.category, FailureCategory.ORCHESTRATION_FAILURE)

    def test_success_not_classified(self):
        """Success should not produce a failure record."""
        result = {
            "status": "success",
            "error": "",
            "latency_ms": 1000,
            "provider": "opencode",
            "model": "test-model",
            "response_text": "Hello world",
        }
        failure = classify_failure(result, 1, 1000, self.config)
        self.assertIsNone(failure)


class TestRetryLogic(unittest.TestCase):
    """Test retry decision logic."""

    def setUp(self):
        self.config = create_default_config()

    def test_orchestration_failure_no_retry(self):
        """ORCHESTRATION_FAILURE should never retry."""
        failure = FailureRecord(
            attempt=1,
            failure_type=FailureType.PROVIDER_ERROR,
            category=FailureCategory.ORCHESTRATION_FAILURE,
            timestamp="2026-01-01T00:00:00Z",
            latency_ms=0,
            error_message="Unknown provider",
            provider="bad",
            model="test",
        )
        retry, reason = should_retry(failure, 1, self.config, 0, [failure])
        self.assertFalse(retry)
        self.assertIn("ORCHESTRATION_FAILURE", reason)

    def test_max_retries_exceeded(self):
        """Should not retry after max_retries."""
        failure = FailureRecord(
            attempt=3,
            failure_type=FailureType.TIMEOUT,
            category=FailureCategory.REAL_AGENT_FAILURE,
            timestamp="2026-01-01T00:00:00Z",
            latency_ms=300000,
            error_message="timeout",
            provider="opencode",
            model="test",
        )
        retry, reason = should_retry(failure, 3, self.config, 500000, [failure])
        self.assertFalse(retry)
        self.assertIn("Max retries", reason)

    def test_retry_storm_detection(self):
        """3 consecutive same-type failures → RETRY_STORM."""
        config = ReliabilityConfig(max_retries=5)
        failures = [
            FailureRecord(
                attempt=i,
                failure_type=FailureType.TIMEOUT,
                category=FailureCategory.REAL_AGENT_FAILURE,
                timestamp="2026-01-01T00:00:00Z",
                latency_ms=300000,
                error_message="timeout",
                provider="opencode",
                model="test",
            )
            for i in range(1, 4)
        ]
        retry, reason = should_retry(failures[-1], 3, config, 900000, failures)
        self.assertFalse(retry)
        self.assertIn("RETRY_STORM", reason)

    def test_normal_retry_allowed(self):
        """First timeout should allow retry."""
        failure = FailureRecord(
            attempt=1,
            failure_type=FailureType.TIMEOUT,
            category=FailureCategory.REAL_AGENT_FAILURE,
            timestamp="2026-01-01T00:00:00Z",
            latency_ms=300000,
            error_message="timeout",
            provider="opencode",
            model="test",
        )
        retry, reason = should_retry(failure, 1, self.config, 300000, [failure])
        self.assertTrue(retry)

    def test_max_latency_exceeded(self):
        """Should not retry if total latency exceeds max."""
        failure = FailureRecord(
            attempt=1,
            failure_type=FailureType.TIMEOUT,
            category=FailureCategory.REAL_AGENT_FAILURE,
            timestamp="2026-01-01T00:00:00Z",
            latency_ms=300000,
            error_message="timeout",
            provider="opencode",
            model="test",
        )
        # Total elapsed = 2 million ms > max 1.8 million
        retry, reason = should_retry(failure, 1, self.config, 2000000, [failure])
        self.assertFalse(retry)
        self.assertIn("latency", reason)


class TestBackoffCalculation(unittest.TestCase):
    """Test exponential backoff calculation."""

    def setUp(self):
        self.config = create_default_config()

    def test_backoff_increases(self):
        """Backoff should increase with each attempt."""
        b1 = compute_backoff(1, self.config)  # 10 * 1.5^0 = 10s = 10000ms
        b2 = compute_backoff(2, self.config)  # 10 * 1.5^1 = 15s = 15000ms
        b3 = compute_backoff(3, self.config)  # 10 * 1.5^2 = 22.5s = 22500ms
        self.assertGreater(b2, b1)
        self.assertGreater(b3, b2)

    def test_backoff_capped(self):
        """Backoff should be capped at 60s."""
        b = compute_backoff(10, self.config)
        self.assertLessEqual(b, 60000)


class TestModelFallback(unittest.TestCase):
    """Test model fallback chain."""

    def test_fallback_chain(self):
        """Should return next model in chain."""
        config = create_default_config(
            model_fallback_chain=["model-a", "model-b", "model-c"]
        )
        next_model = get_fallback_model("model-a", config)
        self.assertEqual(next_model, "model-b")

    def test_fallback_end_of_chain(self):
        """Should return None at end of chain."""
        config = create_default_config(
            model_fallback_chain=["model-a", "model-b"]
        )
        next_model = get_fallback_model("model-b", config)
        self.assertIsNone(next_model)

    def test_fallback_not_in_chain(self):
        """Should return first model if current is not in chain."""
        config = create_default_config(
            model_fallback_chain=["model-a", "model-b"]
        )
        next_model = get_fallback_model("model-x", config)
        self.assertEqual(next_model, "model-a")

    def test_fallback_disabled(self):
        """Should return None when fallback is disabled."""
        config = create_default_config()
        config.enable_model_fallback = False
        config.model_fallback_chain = ["model-a", "model-b"]
        next_model = get_fallback_model("model-a", config)
        self.assertIsNone(next_model)


class TestReliabilityConfig(unittest.TestCase):
    """Test default configuration values are evidence-based."""

    def test_default_config(self):
        config = create_default_config()
        self.assertEqual(config.base_timeout_seconds, 600)  # Phase 7.5: increased from 300
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.backoff_multiplier, 1.5)
        self.assertEqual(config.max_consecutive_failures, 3)
        self.assertTrue(config.enable_model_fallback)


if __name__ == "__main__":
    unittest.main()