#!/usr/bin/env python3
"""
Trace/Telemetry Verification — Test Provider

Verifies that the test provider generates valid trace data through the
full runtime_execute → execute_with_reliability pipeline.

Tests:
  - execution_id / trace_id / trace_file generation via execute()
  - session_id / latency / tokens / output_hash via execute_with_reliability()
  - Trace file is written to disk
  - Failure mode preserves trace metadata
"""

import sys
import os
import re
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_provider import TestProvider, register_test_provider
from runtime_adapter import execute, execute_with_reliability, invoke_runtime


class TestTraceTelemetry(unittest.TestCase):
    """Verify trace/telemetry generation through test provider."""

    @classmethod
    def setUpClass(cls):
        cls.provider = TestProvider()
        register_test_provider(cls.provider)

    def setUp(self):
        self.provider.reset()
        self.provider.set_scenario("success")

    def tearDown(self):
        self.provider.reset()

    # ── Full pipeline (execute) tests ──

    def test_execute_produces_execution_id(self):
        """execute() should generate EXEC-{timestamp} execution_id."""
        result = execute(
            task_id="TEST-TRACE-001",
            task_text="Generate trace test",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn("execution_id", result)
        self.assertRegex(result["execution_id"], r"^EXEC-\d+$")

    def test_execute_produces_trace_id(self):
        """execute() should generate TRACE-EXEC-{timestamp}-{uuid} trace_id."""
        result = execute(
            task_id="TEST-TRACE-002",
            task_text="Generate trace test",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn("trace_id", result)
        self.assertRegex(result["trace_id"], r"^TRACE-EXEC-\d+-[a-f0-9]+$")

    def test_execute_writes_trace_file(self):
        """execute() should write a trace YAML file to disk."""
        result = execute(
            task_id="TEST-TRACE-003",
            task_text="Verify trace file written",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn("trace_file", result)
        self.assertIsNotNone(result["trace_file"])
        self.assertTrue(os.path.isfile(result["trace_file"]),
                        f"Trace file not found: {result['trace_file']}")

        # Verify trace file content
        with open(result["trace_file"]) as f:
            content = f.read()
        self.assertIn("Execution Trace", content)
        self.assertIn(result["execution_id"], content)

    def test_execute_produces_output_hash(self):
        """execute() should generate a hex output_hash."""
        result = execute(
            task_id="TEST-TRACE-004",
            task_text="Verify hash",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn("output_hash", result)
        self.assertRegex(result["output_hash"], r"^[a-f0-9]+$")

    # ── execute_with_reliability (inner) tests ──

    def test_reliability_produces_session_id(self):
        """execute_with_reliability() should include session_id."""
        result = execute_with_reliability(
            task_id="TEST-TRACE-005",
            task_text="Verify session",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn("session_id", result)
        self.assertIsNotNone(result["session_id"])
        self.assertNotEqual(result["session_id"], "")

    def test_reliability_produces_token_usage(self):
        """execute_with_reliability() should include token_usage with total/input/output."""
        result = execute_with_reliability(
            task_id="TEST-TRACE-006",
            task_text="Verify tokens",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        tokens = result.get("tokens", {})
        self.assertIn("total", tokens)
        self.assertIn("input", tokens)
        self.assertIn("output", tokens)
        self.assertIsInstance(tokens["total"], (int, float))

    def test_reliability_produces_latency(self):
        """execute_with_reliability() should include latency_ms."""
        result = execute_with_reliability(
            task_id="TEST-TRACE-007",
            task_text="Verify latency",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn("latency_ms", result)
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_direct_invoke_produces_provider_result(self):
        """invoke_runtime with test_provider should produce a valid provider result."""
        result = invoke_runtime("test_provider", "Test prompt", "test-model", 300)
        self.assertEqual(result["status"], "success")
        self.assertIn("session_id", result)
        self.assertIn("response_text", result)
        self.assertIn("tokens", result)
        self.assertEqual(result["provider"], "test_provider")

    def test_failure_preserves_reliability_trace(self):
        """Even on failure, reliability summary preserves trace metadata."""
        self.provider.set_scenario("timeout")
        result = execute_with_reliability(
            task_id="TEST-TRACE-008",
            task_text="Verify failure trace",
            decision_context={},
            provider="test_provider",
            model="test-model",
        )
        self.assertIn(result["status"], ["error", "timeout"],
                        f"Status should be error or timeout, got: {result['status']}")
        reliability = result.get("reliability", {})
        failures = reliability.get("failures", [])
        self.assertGreater(len(failures), 0,
                           "Failure records should be preserved")


if __name__ == "__main__":
    unittest.main()