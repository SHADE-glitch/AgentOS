"""Deterministic, offline test provider.

Ported from the old ``test_provider.py``: it replaces the real CLI with canned
outcomes so the whole lifecycle can be exercised without a network, a model,
or recursive invocation. Scenarios: success, timeout, no_output,
provider_error, model_failure.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from aos.adapters.base import (
    STATUS_ERROR,
    STATUS_SUCCESS,
    STATUS_TIMEOUT,
    ProviderResult,
)

SCENARIOS = ("success", "timeout", "no_output", "provider_error", "model_failure")

_SUCCESS_RESPONSE = (
    "## Change\n\n"
    "Added the requested behaviour.\n\n"
    "```python\n"
    "def health():\n"
    "    return {'status': 'ok'}\n"
    "```\n\n"
    "Steps:\n"
    "1. Implement the change\n"
    "2. Run the tests\n\n"
    "Tests: 10/10 pass\n"
)


class TestProvider:
    """A provider that never leaves the process."""

    name = "test_provider"

    def __init__(self, scenario: str = "success"):
        self.set_scenario(scenario)
        self._call_count = 0
        self._call_history: list[dict[str, Any]] = []

    def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; valid: {SCENARIOS}")
        self._scenario = scenario

    @property
    def scenario(self) -> str:
        return self._scenario

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list[dict[str, Any]]:
        return list(self._call_history)

    def reset(self) -> None:
        self._call_count = 0
        self._call_history = []
        self._scenario = "success"

    def invoke(
        self, *, prompt: str, model: str = "", cwd: str = "", timeout_seconds: int = 300
    ) -> ProviderResult:
        self._call_count += 1
        started = time.time()
        result = self._build(model, timeout_seconds)
        result.latency_ms = int((time.time() - started) * 1000)
        self._call_history.append(
            {
                "call_number": self._call_count,
                "scenario": self._scenario,
                "latency_ms": result.latency_ms,
                "status": result.status,
            }
        )
        return result

    # ── scenarios ──────────────────────────────────────────────────
    def _build(self, model: str, timeout_seconds: int) -> ProviderResult:
        common = {"provider": self.name, "model": model}
        if self._scenario == "success":
            return ProviderResult(
                status=STATUS_SUCCESS,
                session_id=f"test_ses_{uuid.uuid4().hex[:12]}",
                response_text=_SUCCESS_RESPONSE,
                tokens={"total": 500, "input": 100, "output": 400},
                cost=0.001,
                **common,
            )
        if self._scenario == "timeout":
            return ProviderResult(
                status=STATUS_TIMEOUT,
                error=f"simulated timeout after {timeout_seconds}s",
                **common,
            )
        if self._scenario == "no_output":
            return ProviderResult(
                status=STATUS_ERROR,
                session_id=f"test_ses_{uuid.uuid4().hex[:12]}",
                tokens={"total": 100, "input": 100, "output": 0},
                error="no text response in provider output",
                **common,
            )
        if self._scenario == "provider_error":
            return ProviderResult(status=STATUS_ERROR, error="provider exit code 1", **common)
        return ProviderResult(status=STATUS_ERROR, error="model unavailable or rate limited", **common)


_instance: Optional[TestProvider] = None


def get_provider() -> TestProvider:
    """Return the process-wide test provider singleton."""
    global _instance
    if _instance is None:
        _instance = TestProvider()
    return _instance
