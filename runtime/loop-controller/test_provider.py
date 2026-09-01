#!/usr/bin/env python3
"""
Non-Recursive Test Provider — Phase 5.4

A deterministic, local, no-network test provider for the Agent OS runtime
pipeline. Replaces the OpenCode CLI subprocess with controlled simulation
so that the full loop_controller → runtime_adapter → P0-1 reliability
guard pipeline can be tested without recursive invocation.

Supports 5 scenarios:
  - success: Returns a valid response
  - timeout: Simulates subprocess timeout
  - no_output: Returns empty response
  - provider_error: Returns error status with non-zero exit code
  - model_failure: Returns a provider-level failure

Usage:
    from test_provider import TestProvider, register_test_provider

    provider = TestProvider()
    provider.set_scenario("success")
    register_test_provider(provider)

    result = execute_with_reliability(
        task_id="TEST-001",
        task_text="Test",
        decision_context={},
        provider="test_provider",
    )
"""

import time
import uuid
from datetime import datetime, timezone


class TestProvider:
    """
    Deterministic test provider that simulates runtime outcomes.

    Does NOT call any external model, CLI, or network service.
    Returns canned responses based on the configured scenario.
    """

    SCENARIOS = {
        "success",
        "timeout",
        "no_output",
        "provider_error",
        "model_failure",
    }

    def __init__(self):
        self._scenario = "success"
        self._call_count = 0
        self._call_history = []

    def set_scenario(self, scenario: str):
        """Set the scenario for this provider. Must be one of SCENARIOS."""
        if scenario not in self.SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}. Valid: {self.SCENARIOS}")
        self._scenario = scenario

    @property
    def call_count(self):
        return self._call_count

    @property
    def call_history(self):
        return list(self._call_history)

    def reset(self):
        """Reset call history and counter."""
        self._call_count = 0
        self._call_history = []
        self._scenario = "success"

    def __call__(self, prompt, model, timeout_seconds=300):
        """
        Provider-compatible call signature.
        Returns a dict matching the standard provider result format.
        """
        self._call_count += 1
        call_start = time.time()

        scenario = self._scenario

        if scenario == "success":
            result = self._make_success(prompt, model)

        elif scenario == "timeout":
            # Simulate timeout by sleeping past the timeout
            # In practice, the reliability guard will handle this
            # We simulate the timeout result that the runtime_adapter
            # would get from a subprocess.TimeoutExpired
            result = self._make_timeout(model, timeout_seconds)

        elif scenario == "no_output":
            result = self._make_no_output(prompt, model)

        elif scenario == "provider_error":
            result = self._make_provider_error(model)

        elif scenario == "model_failure":
            result = self._make_model_failure(model)

        else:
            result = self._make_error(model, f"Unknown scenario: {scenario}")

        latency_ms = int((time.time() - call_start) * 1000)
        result["latency_ms"] = latency_ms

        self._call_history.append({
            "call_number": self._call_count,
            "scenario": scenario,
            "latency_ms": latency_ms,
            "returned_status": result["status"],
        })

        return result

    def _make_success(self, prompt, model):
        session_id = f"test_ses_{uuid.uuid4().hex[:12]}"
        return {
            "session_id": session_id,
            "response_text": (
                "## Code Change\n\n"
                "Added health check endpoint to InterviewController.\n\n"
                "```java\n"
                "@GetMapping(\"/health\")\n"
                "public ResponseEntity<String> health() {\n"
                "    return ResponseEntity.ok(\"OK\");\n"
                "}\n"
                "```\n\n"
                "Build: mvn compile -q\n"
                "Tests: mvn test (10/10 pass)\n"
            ),
            "tokens": {"total": 500, "input": 100, "output": 400},
            "cost": 0.001,
            "status": "success",
            "provider": "test_provider",
            "model": model,
            "error": "",
        }

    def _make_timeout(self, model, timeout_seconds):
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "status": "timeout",
            "error": f"Test provider simulated timeout after {timeout_seconds}s",
            "provider": "test_provider",
            "model": model,
        }

    def _make_no_output(self, prompt, model):
        return {
            "session_id": f"test_ses_{uuid.uuid4().hex[:12]}",
            "response_text": "",
            "tokens": {"total": 100, "input": 100, "output": 0},
            "cost": 0.0001,
            "status": "error",
            "error": "No text response in provider output",
            "provider": "test_provider",
            "model": model,
        }

    def _make_provider_error(self, model):
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "status": "error",
            "error": "Provider error: test_provider exit code 1",
            "provider": "test_provider",
            "model": model,
        }

    def _make_model_failure(self, model):
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "status": "error",
            "error": "Model failure: model unavailable or rate limited",
            "provider": "test_provider",
            "model": model,
        }

    def _make_error(self, model, message):
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "status": "error",
            "error": message,
            "provider": "test_provider",
            "model": model,
        }


def register_test_provider(provider):
    """
    Register a TestProvider instance in the runtime_adapter's PROVIDER_DISPATCH
    so that execute_with_reliability(provider="test_provider") can use it.

    Args:
        provider: TestProvider instance
    """
    from runtime_adapter import PROVIDER_DISPATCH
    PROVIDER_DISPATCH["test_provider"] = provider