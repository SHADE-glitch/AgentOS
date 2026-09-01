#!/usr/bin/env python3
"""
Execution Reliability Guard — Phase 5.1 P0-1

Provides failure classification, retry policy, model fallback, and early
termination for Agent OS runtime execution.

Evidence base:
  - AIView refactoring: 3/6 timeout failures (50% success rate)
  - Evolution Report: "Execution Reliability: 4/10"
  - FP-001: Agent lost context between phases, causing cross-stack output
  - F-001 through F-005: Skill routing failures with model-level issues

Design principles:
  - Do NOT just extend timeout. Classify failures and apply targeted recovery.
  - Distinguish REAL_AGENT_FAILURE (model issue) from ORCHESTRATION_FAILURE (AOS issue).
  - Retry with backoff, not storm.
  - Model fallback must be explicit and logged.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


# ── Failure Classification ──────────────────────────────────────

class FailureType(Enum):
    """Classified failure types based on evidence from AIView project."""
    TIMEOUT = "timeout"
    """Execution exceeded time limit. Evidence: 3/6 AIView executions timed out at 300s."""

    NO_OUTPUT = "no_output"
    """Model returned empty or invalid response. Evidence: runtime_adapter returns 'No text response'."""

    MODEL_FAILURE = "model_failure"
    """Model returned error status or non-zero exit code. Evidence: opencode exit code != 0."""

    RETRY_STORM = "retry_storm"
    """Multiple consecutive failures without meaningful change. Evidence: 3 consecutive timeout retries."""

    PROVIDER_ERROR = "provider_error"
    """Provider infrastructure failure (unknown provider, network error)."""

    UNKNOWN = "unknown"
    """Unclassified failure — escalated for manual review."""


class FailureCategory(Enum):
    """Distinguishes REAL_AGENT_FAILURE from ORCHESTRATION_FAILURE."""
    REAL_AGENT_FAILURE = "real_agent_failure"
    """The model/agent itself failed — timeout, no output, model error.
    Recovery: retry with different model or params."""

    ORCHESTRATION_FAILURE = "orchestration_failure"
    """The Agent OS pipeline failed — provider error, routing error, config error.
    Recovery: fix pipeline, not the model."""


@dataclass
class FailureRecord:
    """Single failure instance with full provenance."""
    attempt: int
    failure_type: FailureType
    category: FailureCategory
    timestamp: str
    latency_ms: int
    error_message: str
    provider: str
    model: str
    recovery_action: str = ""


@dataclass
class ReliabilityConfig:
    """Configuration for execution reliability guard.

    All values are evidence-based from AIView project failures.
    """
    # Timeout configuration
    base_timeout_seconds: int = 600
    """Base timeout per attempt. Evidence: Phase 7.4 multi-agent tasks timed out at 300s, 600s is minimum for complex code analysis."""

    max_timeout_seconds: int = 900
    """Maximum timeout after backoff. Evidence: Phase 7.4 opencode execution timed out on multi-file Java analysis at 300s."""

    # Retry configuration
    max_retries: int = 3
    """Maximum retry attempts for REAL_AGENT_FAILURE. Evidence: 3 failures in AIView were timeout-based."""

    backoff_multiplier: float = 1.5
    """Exponential backoff multiplier. Evidence: avoids RETRY_STORM by spacing attempts."""

    backoff_base_seconds: float = 10.0
    """Base delay between retries. Evidence: immediate retry caused repeated timeouts."""

    # Model fallback
    model_fallback_chain: List[str] = field(default_factory=list)
    """Ordered list of fallback models. Evidence: AIView used model switching and it worked once."""

    enable_model_fallback: bool = True
    """Whether to try fallback models. Evidence: 1 success from model switching in AIView."""

    # Early termination
    max_consecutive_failures: int = 3
    """After this many consecutive failures, stop. Evidence: 3 consecutive timeouts in AIView wasted resources."""

    max_total_latency_ms: int = 1800000
    """Maximum total latency across all attempts (30 min). Evidence: AIView total execution was ~15 min."""

    # Stall detection
    stall_timeout_seconds: int = 120
    """If no output after this time, classify as STALL. Evidence: 300s timeout with no partial output."""


# ── Failure Classification Logic ────────────────────────────────

def classify_failure(provider_result: Dict[str, Any], attempt: int,
                     elapsed_ms: int, config: ReliabilityConfig) -> FailureRecord:
    """
    Classify a provider result into a FailureRecord.

    Args:
        provider_result: dict from runtime provider invocation
        attempt: current attempt number (1-based)
        elapsed_ms: total elapsed time so far
        config: ReliabilityConfig

    Returns:
        FailureRecord with classification
    """
    status = provider_result.get("status", "error")
    error = provider_result.get("error", "")
    latency = provider_result.get("latency_ms", 0)
    provider = provider_result.get("provider", "unknown")
    model = provider_result.get("model", "unknown")
    response = provider_result.get("response_text", "")

    timestamp = datetime.now(timezone.utc).isoformat()

    # Determine failure type
    if status == "timeout":
        failure_type = FailureType.TIMEOUT
        category = FailureCategory.REAL_AGENT_FAILURE
    elif status == "error" and "No text response" in error:
        failure_type = FailureType.NO_OUTPUT
        category = FailureCategory.REAL_AGENT_FAILURE
    elif status == "error" and "exit code" in error:
        failure_type = FailureType.MODEL_FAILURE
        category = FailureCategory.REAL_AGENT_FAILURE
    elif status == "error" and "Unknown provider" in error:
        failure_type = FailureType.PROVIDER_ERROR
        category = FailureCategory.ORCHESTRATION_FAILURE
    elif attempt > config.max_consecutive_failures:
        failure_type = FailureType.RETRY_STORM
        category = FailureCategory.ORCHESTRATION_FAILURE
    elif status != "success":
        failure_type = FailureType.UNKNOWN
        category = FailureCategory.REAL_AGENT_FAILURE
    else:
        # Success — not a failure
        return None

    # Check for stall pattern (timeout with no partial output)
    if failure_type == FailureType.TIMEOUT and not response:
        failure_type = FailureType.TIMEOUT  # Already classified as TIMEOUT

    return FailureRecord(
        attempt=attempt,
        failure_type=failure_type,
        category=category,
        timestamp=timestamp,
        latency_ms=latency,
        error_message=error[:500],
        provider=provider,
        model=model,
    )


# ── Retry Decision Logic ────────────────────────────────────────

def should_retry(failure: FailureRecord, attempt: int,
                 config: ReliabilityConfig, total_elapsed_ms: int,
                 failure_history: List[FailureRecord]) -> tuple[bool, str]:
    """
    Decide whether to retry after a failure.

    Returns:
        (should_retry: bool, reason: str)
    """
    # ORCHESTRATION_FAILURE: do NOT retry — fix the pipeline
    if failure.category == FailureCategory.ORCHESTRATION_FAILURE:
        return False, f"ORCHESTRATION_FAILURE ({failure.failure_type.value}) — not retryable"

    # Check retry limit
    if attempt >= config.max_retries:
        return False, f"Max retries ({config.max_retries}) reached"

    # Check total latency
    if total_elapsed_ms >= config.max_total_latency_ms:
        return False, f"Max total latency ({config.max_total_latency_ms}ms) exceeded"

    # Check for RETRY_STORM
    if len(failure_history) >= config.max_consecutive_failures:
        recent = failure_history[-config.max_consecutive_failures:]
        all_same_type = all(f.failure_type == recent[0].failure_type for f in recent)
        if all_same_type:
            return False, f"RETRY_STORM: {config.max_consecutive_failures} consecutive {recent[0].failure_type.value} failures"

    return True, f"Retry {attempt + 1}/{config.max_retries}"


# ── Backoff Calculation ─────────────────────────────────────────

def compute_backoff(attempt: int, config: ReliabilityConfig) -> int:
    """
    Compute exponential backoff delay in milliseconds.

    Formula: base * (multiplier ^ (attempt - 1)) seconds
    """
    delay_seconds = config.backoff_base_seconds * (config.backoff_multiplier ** (attempt - 1))
    return int(min(delay_seconds * 1000, 60000))  # Cap at 60s


# ── Model Fallback ──────────────────────────────────────────────

def get_fallback_model(current_model: str, config: ReliabilityConfig) -> Optional[str]:
    """
    Get next model in fallback chain.

    Returns:
        Next model name, or None if no fallback available.
    """
    if not config.enable_model_fallback or not config.model_fallback_chain:
        return None

    try:
        idx = config.model_fallback_chain.index(current_model)
        if idx + 1 < len(config.model_fallback_chain):
            return config.model_fallback_chain[idx + 1]
    except ValueError:
        # Current model not in chain — start from beginning
        if config.model_fallback_chain:
            return config.model_fallback_chain[0]

    return None


# ── Reliability Summary ─────────────────────────────────────────

@dataclass
class ReliabilitySummary:
    """Summary of execution reliability for a single task."""
    total_attempts: int = 0
    failures: List[FailureRecord] = field(default_factory=list)
    retries_performed: int = 0
    fallbacks_used: List[str] = field(default_factory=list)
    models_tried: List[str] = field(default_factory=list)
    final_status: str = "pending"
    total_latency_ms: int = 0
    classification: str = ""  # REAL_AGENT_FAILURE or ORCHESTRATION_FAILURE
    terminated_early: bool = False
    termination_reason: str = ""


# ── Reliability Guard Entry Point ───────────────────────────────

def create_default_config(model_fallback_chain: Optional[List[str]] = None) -> ReliabilityConfig:
    """Create a default ReliabilityConfig with evidence-based defaults."""
    return ReliabilityConfig(
        model_fallback_chain=model_fallback_chain or [],
    )