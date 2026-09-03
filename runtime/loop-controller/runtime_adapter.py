#!/usr/bin/env python3
"""
Runtime Adapter — Phase 5.10.3 (Runtime Neutralization) + Phase 5.1 P0-1 (Reliability) + P0-2 (Cross-Stack)

Bridges DecisionContext → Runtime Provider → Trace.

DecisionContext + Task → Runtime Provider Abstraction → trace YAML

This adapter:
  1. Constructs a prompt with memory context as SUPPORTING input
  2. Detects project tech stack and includes stack context (P0-2)
  3. Dispatches to the appropriate runtime provider via invoke_runtime()
  4. Applies execution reliability guard with retry/fallback (P0-1)
  5. Parses provider output (session_id, tokens, response, latency)
  6. Writes a trace file to runtime/traces/
  7. Returns ExecutionResult

Provider abstraction: Agent OS core never references a specific runtime.
Providers are resolved via the runtime contract.

CHANGE_ID: P0-1-RELIABILITY
ROOT_CAUSE: 3/6 timeout failures in AIView project (50% success rate)
EVIDENCE: AIView Evolution Report, loop-controller/state/*.yaml
CHANGE: Added execution_reliability module integration, retry with backoff, model fallback
FILE: runtime_adapter.py
WHY: Flat 300s timeout with no retry caused 50% failure rate
RISK: Low — retry only on REAL_AGENT_FAILURE, not ORCHESTRATION_FAILURE
VALIDATION: Regression test in tests/test_p0_1_reliability.py

CHANGE_ID: P0-2-CROSSSTACK
ROOT_CAUSE: Agent produced Python code for Java/Spring Boot project (AIView)
EVIDENCE: FP-003 Cross-Stack Output Contamination, evolution/cases/AIView/case.md
CHANGE: Added tech stack detection and stack-aware prompt building
FILE: runtime_adapter.py
WHY: Without stack context, agent defaults to Python ecosystem
RISK: Low — stack context is additive, doesn't change existing behavior
VALIDATION: Regression test in tests/test_p0_2_crossstack.py
"""

import subprocess
import json
import yaml
import os
import sys
import hashlib
import time
import uuid
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass

BASE = "/home/shade/.agents"
TRACES_DIR = os.path.join(BASE, "runtime", "traces")
LOOP_CONTROLLER_DIR = os.path.join(BASE, "runtime", "loop-controller")

# Defaults — sourced from environment, host, or CLI (never hardcoded)
DEFAULT_PROVIDER = os.environ.get("AOS_RUNTIME_PROVIDER", "opencode")
DEFAULT_MODEL = os.environ.get("AOS_RUNTIME_MODEL", "")

# Phase 5.1 P0-1: Execution Reliability Guard
sys.path.insert(0, LOOP_CONTROLLER_DIR)
from execution_reliability import (
    ReliabilityConfig,
    FailureRecord,
    FailureType,
    FailureCategory,
    ReliabilitySummary,
    classify_failure,
    should_retry,
    compute_backoff,
    get_fallback_model,
    create_default_config,
)

# Phase 5.1 P0-2: Cross-Stack Protection
from cross_stack_guard import (
    detect_tech_stack,
    validate_output_stack,
    build_stack_context,
    CrossStackResult,
    TechStack,
)

# Phase 5.9: Atomic write utility
from file_utils import atomic_yaml_write


def generate_execution_id():
    """Generate a unique execution ID."""
    ts = int(time.time())
    return f"EXEC-{ts}"


def generate_trace_id(execution_id):
    """Generate a trace ID."""
    suffix = uuid.uuid4().hex[:12]
    return f"TRACE-{execution_id}-{suffix}"


def generate_loop_id():
    """Generate a unique loop ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"LOOP-{ts}"


def compute_output_hash(text):
    """Compute SHA256 hash of output text."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _serialize_reliability(summary, failures):
    """
    Phase 5.9: Convert ReliabilitySummary and FailureRecord dataclass objects
    to plain dicts for YAML-safe serialization (no Python object tags).
    """
    result = {
        "total_attempts": summary.total_attempts,
        "retries_performed": summary.retries_performed,
        "fallbacks_used": summary.fallbacks_used,
        "models_tried": summary.models_tried,
        "final_status": summary.final_status,
        "total_latency_ms": summary.total_latency_ms,
        "classification": summary.classification,
        "terminated_early": summary.terminated_early,
        "termination_reason": summary.termination_reason,
        "failures": [
            {
                "attempt": f.attempt,
                "failure_type": f.failure_type.value if hasattr(f.failure_type, 'value') else str(f.failure_type),
                "category": f.category.value if hasattr(f.category, 'value') else str(f.category),
                "timestamp": f.timestamp,
                "latency_ms": f.latency_ms,
                "error_message": f.error_message,
                "provider": f.provider,
                "model": f.model,
                "recovery_action": f.recovery_action,
            }
            for f in failures
        ],
    }
    return result


# ── Phase 8.2.1.4: Semantic Memory Injection Helpers ────────────────
# These format memory metadata into actionable decision guidance
# that the agent can use to influence its reasoning.

_TYPE_GUIDANCE_TEMPLATES = {
    "task": (
        "This task pattern was validated: use it as a reference for similar "
        "engineering tasks. Review the approach and adapt to current context."
    ),
    "failure": (
        "This failure pattern was observed: identify whether the current task "
        "risks repeating the same mistake. Apply preventive measures."
    ),
    "success": (
        "This approach succeeded in a prior execution: consider adopting "
        "its strategy, but verify it fits the current problem domain."
    ),
    "pattern": (
        "This design pattern was extracted from successful executions: "
        "apply it if the current task shares the same architectural context."
    ),
    "anti-pattern": (
        "This anti-pattern was identified from failed executions: "
        "check whether the current task exhibits the same warning signs."
    ),
    "hypothesis": (
        "[UNVALIDATED] This hypothesis has not been validated through "
        "runtime execution. Treat it as a suggestion, not an established rule."
    ),
}

_TYPE_ACTION_TEMPLATES = {
    "task": "Reference this pattern when solving similar tasks.",
    "failure": "Avoid this failure mode. Apply its preventive lesson.",
    "success": "Consider this successful strategy. Verify domain fit.",
    "pattern": "Apply this design pattern where applicable.",
    "anti-pattern": "Check for this anti-pattern. Mitigate if found.",
    "hypothesis": "Test this hypothesis. Do not rely on it as established truth.",
}

_MEMORY_INJECTION_LIMIT = 5


def _evidence_icon(evidence_level: str) -> str:
    """Return a visual icon for evidence level."""
    icons = {
        "runtime_validated": "✓",
        "benchmark_evaluated": "◆",
        "observed": "○",
        "hypothesis": "⚠",
        "unknown": "?",
    }
    return icons.get(evidence_level, "?")


def _evidence_label(evidence_level: str, success_rate: float) -> str:
    """Return a human-readable credibility label."""
    if evidence_level == "runtime_validated":
        return "validated-in-runtime"
    elif evidence_level == "benchmark_evaluated":
        return "benchmark-tested"
    elif evidence_level == "observed":
        return "observed"
    elif evidence_level == "hypothesis":
        return "UNVALIDATED"
    else:
        sr = ""
        if success_rate > 0:
            sr = f" sr={success_rate:.2f}"
        return f"unknown{ sr}"


def _format_memory_guidance(memory: dict, rank: int) -> str:
    """Format a single memory as semantic decision guidance.

    Produces a structured guidance line that includes:
      - memory_id (provenance)
      - type label and evidence_level (credibility)
      - success_rate (reliability)
      - category and tags (domain context)
      - generated guidance (actionable direction)
      - recommended action (what to do with this memory)
    """
    mid = memory.get("memory_id", "?")
    mtype = memory.get("type", "memory")
    evidence = memory.get("evidence_level", "unknown")
    success_rate = memory.get("success_rate", 0.0)
    category = memory.get("category", "unknown")
    tags = memory.get("tags", [])
    confidence = memory.get("confidence", "low")
    score = memory.get("final_score", 0.0)

    evidence_icon = _evidence_icon(evidence)
    credibility = _evidence_label(evidence, success_rate)

    tag_str = ", ".join(tags[:5]) if tags else "none"

    guidance = _TYPE_GUIDANCE_TEMPLATES.get(mtype, _TYPE_GUIDANCE_TEMPLATES["task"])
    action = _TYPE_ACTION_TEMPLATES.get(mtype, _TYPE_ACTION_TEMPLATES["task"])

    if memory.get("is_hypothesis") or mtype == "hypothesis":
        evidence_icon = "⚠"
        credibility = "UNVALIDATED"

    return (
        f"[{mid}] {evidence_icon} {mtype} | {credibility} | "
        f"success_rate={success_rate:.2f} | confidence={confidence} | "
        f"score={score:.2f}\n"
        f"  Category: {category} | Tags: {tag_str}\n"
        f"  Guidance: {guidance}\n"
        f"  Action: {action}"
    )


def build_prompt(task_text, decision_context, project_root=""):
    """
    Construct the prompt for the runtime provider.

    Phase 8.2.1.4: Memory is presented as semantic decision guidance
    with evidence level, success rate, guidance, and recommended action.
    Stack context is included (P0-2).
    Skill context is included from real Skill Loader (Phase 5.7).

    Args:
        task_text: str, the task to execute
        decision_context: dict, from loop_controller (includes route_decision, skill_context)
        project_root: str, path to project root for stack detection (P0-2)
    """
    mem = decision_context.get("memories", [])
    hyp = decision_context.get("hypotheses", [])
    classification = decision_context.get("classification", {})
    route_decision = decision_context.get("route_decision", {})
    skill_context = decision_context.get("skill_context", {})

    category = classification.get("category", "backend")
    domains = classification.get("domains", [])
    domain_str = ", ".join(domains) if domains else "general"

    parts = []

    # Phase 5.7: Use REAL Skill prompt prefix from skill_loader
    prompt_prefix = skill_context.get("prompt_prefix", "")
    if prompt_prefix:
        parts.append(prompt_prefix)
    else:
        parts.append(f"You are an expert software engineer working on a {category} task.")
        parts.append(f"Domain: {domain_str}")

    parts.append("")

    # P0-2: Tech stack context
    if project_root and os.path.isdir(project_root):
        stack_context = build_stack_context(project_root)
        if stack_context:
            parts.append(stack_context)
            parts.append("")

    # Phase 8.2.1.4: Semantic Memory Injection
    # Memory is presented as structured decision guidance with
    # evidence level, success rate, guidance, and recommended action.
    if mem:
        parts.append("[RELEVANT MEMORY — Decision Guidance]")
        parts.append("")
        for i, m in enumerate(mem[:_MEMORY_INJECTION_LIMIT]):
            parts.append(_format_memory_guidance(m, i + 1))
            parts.append("")
        # Track injected memories for telemetry
        decision_context["injected_ids"] = [m.get("memory_id") for m in mem[:_MEMORY_INJECTION_LIMIT]]
        decision_context["injected_count"] = len(decision_context["injected_ids"])
        decision_context["injection_format"] = "semantic_guidance"
    else:
        decision_context["injected_ids"] = []
        decision_context["injected_count"] = 0
        decision_context["injection_format"] = "none"
    if hyp:
        parts.append("[UNVALIDATED HYPOTHESES — Verify before use, do not rely]")
        parts.append("")
        for i, h in enumerate(hyp[:_MEMORY_INJECTION_LIMIT]):
            parts.append(_format_memory_guidance(h, i + 1))
            parts.append("")
        decision_context["injected_hypothesis_ids"] = [h.get("memory_id") for h in hyp[:_MEMORY_INJECTION_LIMIT]]
        decision_context["injected_hypothesis_count"] = len(decision_context["injected_hypothesis_ids"])
    else:
        decision_context["injected_hypothesis_ids"] = []
        decision_context["injected_hypothesis_count"] = 0

    # Task
    parts.append("## Task")
    parts.append(task_text)
    parts.append("")
    parts.append("Provide a thorough, structured response. Include specific steps, code examples, or configuration recommendations as appropriate.")

    return "\n".join(parts)


# ── Provider Invocation ──────────────────────────────────────────

def _invoke_opencode_provider(prompt, model, timeout_seconds=600):
    """OpenCode provider: call opencode CLI and parse JSONL output.

    Phase 7.5: Default timeout increased from 300s to 600s.
    Complex multi-agent code analysis tasks require longer execution windows.
    """
    cmd = [
        "opencode", "run",
        "--pure",
        "--format", "json",
        "--auto",
        "--model", model,
        prompt,
    ]

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "latency_ms": int(timeout_seconds * 1000),
            "status": "timeout",
            "error": f"opencode run exceeded {timeout_seconds}s timeout",
            "provider": "opencode",
            "model": model,
        }

    latency_ms = int((time.time() - start_time) * 1000)

    if result.returncode != 0:
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "latency_ms": latency_ms,
            "status": "error",
            "error": f"opencode exit code {result.returncode}: {result.stderr[:500]}",
            "provider": "opencode",
            "model": model,
        }

    # Parse JSONL output
    response_text = ""
    session_id = ""
    tokens = {"total": 0, "input": 0, "output": 0}
    cost = 0.0

    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        obj_type = obj.get("type", "")

        if obj_type == "text":
            part = obj.get("part", {})
            session_id = part.get("sessionID", session_id)
            response_text = part.get("text", "")

        elif obj_type == "step_finish":
            part = obj.get("part", {})
            t = part.get("tokens", {})
            if t:
                tokens = {
                    "total": t.get("total", 0),
                    "input": t.get("input", 0),
                    "output": t.get("output", 0),
                    "reasoning": t.get("reasoning", 0),
                    "cache_read": t.get("cache", {}).get("read", 0),
                    "cache_write": t.get("cache", {}).get("write", 0),
                }
            cost = part.get("cost", 0.0)
            session_id = part.get("sessionID", session_id)

    if not response_text:
        return {
            "session_id": session_id,
            "response_text": "",
            "tokens": tokens,
            "cost": cost,
            "latency_ms": latency_ms,
            "status": "error",
            "error": "No text response in OpenCode output",
            "provider": "opencode",
            "model": model,
        }

    return {
        "session_id": session_id,
        "response_text": response_text,
        "tokens": tokens,
        "cost": cost,
        "latency_ms": latency_ms,
        "status": "success",
        "provider": "opencode",
        "model": model,
    }


# Provider dispatch table
PROVIDER_DISPATCH = {
    "opencode": _invoke_opencode_provider,
}


def invoke_runtime(provider, prompt, model, timeout_seconds=600):
    """
    Dispatch to the appropriate runtime provider.

    Phase 7.5: Default timeout increased from 300s to 600s.

    Args:
        provider: str, provider name (opencode, ...)
        prompt: str, the constructed prompt
        model: str, provider-specific model identifier
        timeout_seconds: int, timeout for this invocation (P0-1)

    Returns:
        dict: standard provider result (status, session_id, tokens, etc.)
    """
    invoke_fn = PROVIDER_DISPATCH.get(provider)
    if invoke_fn is None:
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "latency_ms": 0,
            "status": "error",
            "error": f"Unknown provider: {provider}",
            "provider": provider,
            "model": model,
        }
    return invoke_fn(prompt, model, timeout_seconds)


# ── P0-1: Reliable Execution ─────────────────────────────────────

def execute_with_reliability(task_id, task_text, decision_context,
                             model="", provider="opencode",
                             project_root="",
                             reliability_config=None,
                             timeout_seconds=None):
    """
    Execute a task with reliability guard (P0-1).

    Phase 7.5: Added timeout_seconds override for per-task timeout control.

    Features:
      - Retry with exponential backoff on REAL_AGENT_FAILURE
      - Model fallback chain
      - Early termination on RETRY_STORM or ORCHESTRATION_FAILURE
      - Failure classification and tracking
      - Per-task timeout override (timeout_seconds)

    Args:
        task_id: str
        task_text: str
        decision_context: dict from retrieval adapter
        model: str, primary model
        provider: str, runtime provider
        project_root: str, project root for stack detection (P0-2)
        reliability_config: ReliabilityConfig or None (uses defaults)
        timeout_seconds: int or None. If set, overrides the config base_timeout.

    Returns:
        dict: execution result with reliability summary
    """
    if reliability_config is None:
        reliability_config = create_default_config()

    # Phase 7.5: Apply per-task timeout override if provided
    if timeout_seconds is not None:
        reliability_config.base_timeout_seconds = timeout_seconds
        reliability_config.max_timeout_seconds = max(timeout_seconds, reliability_config.max_timeout_seconds)

    summary = ReliabilitySummary()
    current_model = model
    total_start = time.time()
    failure_history = []

    # Build prompt
    prompt = build_prompt(task_text, decision_context, project_root=project_root)

    for attempt in range(1, reliability_config.max_retries + 2):  # +2 for initial + max_retries
        summary.total_attempts = attempt
        summary.models_tried.append(current_model)

        # Calculate timeout with backoff
        timeout_seconds = min(
            reliability_config.base_timeout_seconds * (reliability_config.backoff_multiplier ** (attempt - 1)),
            reliability_config.max_timeout_seconds
        )

        # Execute
        result = invoke_runtime(provider, prompt, current_model, timeout_seconds=int(timeout_seconds))
        total_elapsed = int((time.time() - total_start) * 1000)

        # Check success
        if result.get("status") == "success":
            summary.final_status = "success"
            summary.total_latency_ms = total_elapsed

            # P0-2: Cross-stack validation on successful output
            cross_stack = None
            if project_root and os.path.isdir(project_root):
                cross_stack = validate_output_stack(project_root, result.get("response_text", ""))
                if cross_stack.contamination_detected:
                    result["cross_stack_warning"] = {
                        "detected": True,
                        "contaminated_language": cross_stack.contaminated_language,
                        "warnings": cross_stack.warnings,
                        "details": cross_stack.contamination_details,
                    }

            result["reliability"] = {
                "summary": {
                    "total_attempts": summary.total_attempts,
                    "retries_performed": summary.retries_performed,
                    "fallbacks_used": summary.fallbacks_used,
                    "models_tried": summary.models_tried,
                    "final_status": summary.final_status,
                    "total_latency_ms": summary.total_latency_ms,
                    "classification": "success",
                },
                "cross_stack": {
                    "contamination_detected": cross_stack.contamination_detected if cross_stack else False,
                    "contaminated_language": cross_stack.contaminated_language if cross_stack else "",
                    "warnings": cross_stack.warnings if cross_stack else [],
                } if cross_stack else None,
            }
            return result

        # Classify failure
        failure = classify_failure(result, attempt, total_elapsed, reliability_config)
        if failure is None:
            # Should not happen if status != success, but handle gracefully
            failure = FailureRecord(
                attempt=attempt,
                failure_type=FailureType.UNKNOWN,
                category=FailureCategory.REAL_AGENT_FAILURE,
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=result.get("latency_ms", 0),
                error_message=result.get("error", "Unknown error"),
                provider=provider,
                model=current_model,
            )

        failure_history.append(failure)
        summary.failures.append(failure)
        summary.classification = failure.category.value

        # Decide retry
        retry, reason = should_retry(failure, attempt, reliability_config, total_elapsed, failure_history)

        if not retry:
            summary.final_status = "failed"
            summary.total_latency_ms = total_elapsed
            summary.terminated_early = True
            summary.termination_reason = reason

            result["reliability"] = {
                "summary": _serialize_reliability(summary, failure_history),
                "failures": _serialize_reliability(summary, failure_history)["failures"],
            }
            return result

        summary.retries_performed = attempt

        # Try model fallback
        fallback_model = get_fallback_model(current_model, reliability_config)
        if fallback_model and fallback_model != current_model:
            current_model = fallback_model
            summary.fallbacks_used.append(fallback_model)
            failure.recovery_action = f"fallback to model: {fallback_model}"
        else:
            failure.recovery_action = f"retry {attempt}/{reliability_config.max_retries}"

        # Backoff before retry
        delay_ms = compute_backoff(attempt, reliability_config)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    # Max attempts reached
    summary.final_status = "failed"
    summary.total_latency_ms = int((time.time() - total_start) * 1000)
    summary.terminated_early = True
    summary.termination_reason = "Max attempts exhausted"

    # Build failure result with reliability info
    failure_result = {
        "session_id": "",
        "response_text": "",
        "tokens": {"total": 0, "input": 0, "output": 0},
        "cost": 0,
        "latency_ms": summary.total_latency_ms,
        "status": "error",
        "error": "All execution attempts failed",
        "provider": provider,
        "model": current_model,
        "reliability": {
            "summary": _serialize_reliability(summary, failure_history),
            "failures": _serialize_reliability(summary, failure_history)["failures"],
        },
    }
    return failure_result


# ── Phase 8.2.1.5: Decision Influence Attribution ─────────────────

# Influence levels ordered by strength (least → most).
# Lower levels are subsumed by higher levels.
INFLUENCE_LEVELS = {
    "none": 0,
    "confirmation": 1,
    "hypothesis_used": 2,
    "hypothesis_confirmed": 3,
    "hypothesis_changed_decision": 4,
}

# Keywords that indicate the agent is actively engaging with a hypothesis
# (testing, validating, or refining it), beyond passive mention.
_HYPOTHESIS_ENGAGEMENT_PATTERNS = [
    r"(?:hypothesis|H-\d+|unvalidated|unverified).{0,80}(?:confirmed|validated|verified|supports|aligns)",
    r"(?:test|validate|verify|check).{0,40}(?:hypothesis|H-\d+|assumption)",
    r"(?:hypothesis|H-\d+).{0,40}(?:holds|correct|accurate|should be)",
    r"(?:based on|following|according to).{0,40}(?:hypothesis|H-\d+)",
    r"(?:suggest|recommend|propose).{0,80}(?:hypothesis|H-\d+)",
    r"(?:aligns with|consistent with|matches).{0,40}(?:hypothesis|H-\d+)",
    r"H-\d{3,4}",
    r"(?:⚠|UNVALIDATED).{0,60}(?:applies|relevant|useful|helpful)",
]

# Keywords that indicate a hypothesis changed the agent's decision.
_HYPOTHESIS_DECISION_CHANGE_PATTERNS = [
    r"(?:changed|reversed|revised|updated|adjusted|shifted).{0,40}(?:decision|conclusion|approach|recommendation)",
    r"(?:hypothesis|H-\d+|unvalidated).{0,60}(?:changed|altered|transformed|redirected)",
    r"(?:without|absent).{0,20}(?:hypothesis|H-\d+).{0,40}(?:would have|might have|could have)",
    r"(?:contrary to|despite|even though).{0,40}(?:initial|original|prior).{0,20}(?:assumption|belief|approach)",
    r"(?:before|prior to).{0,20}(?:hypothesis|H-\d+).{0,60}(?:after|now|currently)",
]


# Patterns that indicate negation — if matched, term mentions are discounted.
_NEGATION_PATTERNS = [
    r"(?:unrelated to|not about|not relevant to|irrelevant to|nothing to do with)\s.{0,40}",
    r"(?:does not|doesn't|is not|isn't|not).{0,30}(?:apply|relate|relevant|involve|concern|needed|required|necessary)",
    r"(?:no|not)\s.{0,40}(?:needed|required|necessary|relevant|applicable)",
]


def _detect_hypothesis_engagement(agent_response: str, hypotheses: list) -> dict:
    """Detect if and how the agent engaged with each hypothesis.

    Returns a dict mapping hypothesis_id → engagement_info.
    """
    import re
    engagement = {}

    # Pre-compute negation context
    has_negation = any(re.search(p, agent_response, re.IGNORECASE) for p in _NEGATION_PATTERNS)

    for hyp in hypotheses:
        hid = hyp.get("memory_id", "")
        if not hid:
            continue

        # Check if the hypothesis ID appears in the response
        id_mentioned = hid in agent_response

        # Check if key terms from the hypothesis appear in the response
        tags = hyp.get("tags", [])
        guidance = hyp.get("guidance", "")
        key_terms = list(tags) + [w for w in guidance.split() if len(w) > 4]
        term_matches = sum(1 for t in key_terms if t in agent_response)

        # Check engagement patterns
        engaged = False
        changed_decision = False
        for pattern in _HYPOTHESIS_ENGAGEMENT_PATTERNS:
            if re.search(pattern, agent_response, re.IGNORECASE):
                engaged = True
                break
        for pattern in _HYPOTHESIS_DECISION_CHANGE_PATTERNS:
            if re.search(pattern, agent_response, re.IGNORECASE):
                changed_decision = True
                break

        # Fallback: if ID is mentioned or terms match significantly, consider engaged
        # BUT discount if the overall response has negation context and no explicit ID mention
        if not engaged and (id_mentioned or (term_matches >= 2 and not has_negation)):
            engaged = True

        level = "none"
        if changed_decision:
            level = "hypothesis_changed_decision"
        elif engaged:
            level = "hypothesis_confirmed" if term_matches >= 3 else "hypothesis_used"

        engagement[hid] = {
            "referenced": id_mentioned or (term_matches > 0 and not has_negation),
            "engagement_level": level,
            "id_mentioned": id_mentioned,
            "term_matches": term_matches,
            "changed_decision": changed_decision,
        }

    return engagement


def _determine_influence(memories_used: list, hyp_list: list,
                         agent_response: str = "") -> dict:
    """Determine the decision influence with hypothesis-aware attribution.

    Returns a dict with:
      - influence: str (primary influence level)
      - influence_breakdown: dict (per-memory/hypothesis attribution)
      - provenance: list (per-contributor provenance records)
    """
    provenance = []
    influence_breakdown = {}
    max_influence_level = 0
    primary_influence = "none"

    # 1. Established memory influence (existing behavior)
    for mem in memories_used:
        mid = mem.get("memory_id", "?")
        influence_breakdown[mid] = {
            "type": "established",
            "influence": "confirmation",
            "memory_id": mid,
            "retrieval_score": mem.get("final_score", mem.get("static_relevance", 0)),
        }
        provenance.append({
            "memory_id": mid,
            "memory_type": mem.get("type", "established"),
            "retrieval_score": mem.get("final_score", 0),
            "injection_format": "semantic_guidance",
            "agent_reference": "implicit_usage",
        })
        max_influence_level = max(max_influence_level, INFLUENCE_LEVELS["confirmation"])

    # 2. Hypothesis influence (NEW in Phase 8.2.1.5)
    if hyp_list:
        hyp_engagement = _detect_hypothesis_engagement(agent_response, hyp_list) if agent_response else {}

        for hyp in hyp_list:
            hid = hyp.get("memory_id", "")
            if not hid:
                continue

            eng = hyp_engagement.get(hid, {})
            eng_level = eng.get("engagement_level", "none")

            influence_breakdown[hid] = {
                "type": "hypothesis",
                "influence": eng_level,
                "memory_id": hid,
                "retrieval_score": hyp.get("final_score", hyp.get("static_relevance", 0)),
                "referenced": eng.get("referenced", False),
                "id_mentioned": eng.get("id_mentioned", False),
                "term_matches": eng.get("term_matches", 0),
                "changed_decision": eng.get("changed_decision", False),
            }

            if eng_level != "none":
                provenance.append({
                    "memory_id": hid,
                    "memory_type": "hypothesis",
                    "retrieval_score": hyp.get("final_score", 0),
                    "injection_format": "hypothesis_injection",
                    "agent_reference": "explicit" if eng.get("id_mentioned") else "semantic",
                })

            eng_level_num = INFLUENCE_LEVELS.get(eng_level, 0)
            max_influence_level = max(max_influence_level, eng_level_num)

    # 3. Determine primary influence
    for level_name, level_num in INFLUENCE_LEVELS.items():
        if level_num == max_influence_level:
            primary_influence = level_name
            break

    return {
        "influence": primary_influence,
        "influence_breakdown": influence_breakdown,
        "provenance": provenance,
    }


# ── Trace Building ───────────────────────────────────────────────

def build_trace(execution_id, trace_id, task_id, task_text, decision_context,
                provider, model, runtime_result, pipeline_timestamps=None,
                code_validation_result=None):
    """
    Build a trace YAML dict. Provider-agnostic.

    Phase 5.7: Uses REAL Router and Skill decisions from decision_context,
    NOT simulated values. Pipeline timestamps are REAL.

    pipeline_timestamps: dict with real timestamps from loop_controller:
        task_received, routing_completed, memory_retrieved,
        orchestration_completed, skill_loaded, agent_started, agent_completed
    code_validation_result: CodeValidationResult from code_validator (Phase 6.2)
    """
    now = datetime.now(timezone.utc).isoformat()
    classification = decision_context.get("classification", {})

    if pipeline_timestamps is None:
        pipeline_timestamps = {}

    ts = pipeline_timestamps

    # Phase 5.7: Use REAL route decision from loop_controller
    route_decision = decision_context.get("route_decision", {})
    skill_context = decision_context.get("skill_context", {})

    # Memory retrieval section (real data)
    mem_list = decision_context.get("memories", [])
    hyp_list = decision_context.get("hypotheses", [])

    memories_considered = []
    memories_used = []
    for m in mem_list:
        memories_considered.append({
            "memory_id": m["memory_id"],
            "type": m.get("type", "?"),
            "category": m.get("category", "?"),
            "relevance_score": m.get("static_relevance", 0),
            "evidence_weight": m.get("confidence_score", 0),
            "final_score": m.get("final_score", 0),
            "used": True,
            "match_reasons": m.get("match_reasons", []),
        })
        memories_used.append(m["memory_id"])

    for h in hyp_list:
        memories_considered.append({
            "memory_id": h["memory_id"],
            "type": "hypothesis",
            "category": h.get("category", "?"),
            "relevance_score": h.get("static_relevance", 0),
            "evidence_weight": h.get("confidence_score", 0),
            "final_score": h.get("final_score", 0),
            "used": False,
            "rejection_reason": "Hypothesis — not an established rule",
            "match_reasons": h.get("match_reasons", []),
        })

    # Phase 8.2.1.5: Hypothesis-aware influence attribution
    agent_response = runtime_result.get("response_text", "")
    attribution = _determine_influence(mem_list, hyp_list, agent_response)
    influence = attribution["influence"]
    influence_breakdown = attribution["influence_breakdown"]
    influence_provenance = attribution["provenance"]

    # Phase 5.7: REAL Router section (from agent_router, not simulated)
    intent = route_decision.get("intent", classification.get("category", "backend"))
    lead_skill = route_decision.get("lead_skill", "backend-architect")
    support_skills = route_decision.get("support_skills", [])
    confidence = route_decision.get("confidence", "medium")
    rules_applied = route_decision.get("rules_applied", [])

    # Phase 5.7: REAL Skill section
    skills_loaded = skill_context.get("skills_loaded", [lead_skill])
    lead_skill_loaded = skill_context.get("lead_skill", {}).get("loaded", False)
    support_skills_loaded = [s.get("name", "") for s in skill_context.get("support_skills", [])]

    # Orchestrator section (derived from real skill context)
    team_size = len(skills_loaded)
    single_agent = team_size <= 1

    # P0-1: Reliability info
    reliability_info = runtime_result.get("reliability", {})

    # P0-2: Cross-stack info
    cross_stack_info = runtime_result.get("cross_stack_warning", {})

    trace = {
        "execution_id": execution_id,
        "trace_id": trace_id,
        "task_id": task_id,
        "task_text": task_text,
        "domain": intent.capitalize(),
        "difficulty": classification.get("difficulty", "medium"),
        "memory_mode": "on" if decision_context.get("retrieved") else "off",
        "provider": provider,
        "model": model,
        "status": runtime_result["status"],
        "phase": "5.7",

        "pipeline": {
            "step_timestamps": {
                "task_received": ts.get("task_received", now),
                "memory_retrieved": ts.get("memory_retrieved", now),
                "routing_completed": ts.get("routing_completed", now),
                "skill_loaded": ts.get("skill_loaded", now),
                "orchestration_completed": ts.get("orchestration_completed", now),
                "agent_started": ts.get("agent_started", now),
                "agent_completed": ts.get("agent_completed", now),
            }
        },

        "entry": decision_context.get("entry_metadata", {
            "entry_type": "unknown",
            "note": "no entry metadata provided",
        }),

        "router": {
            "intent": intent,
            "lead_skill": lead_skill,
            "support_skills": support_skills,
            "confidence": confidence,
            "memory_influence": route_decision.get("memory_influence", "none"),
            "rules_applied": rules_applied,
            "source": "agent_router.route() — Phase 5.7 REAL Router",
        },

        "memory_retrieval": {
            "mode": "on" if decision_context.get("retrieved") else "off",
            "total_retrieved": len(memories_considered),
            "memories_considered": memories_considered,
            "memories_used": memories_used,
            "hypotheses_injected": [h.get("memory_id", "") for h in hyp_list],
            "influence": influence,
            "influence_breakdown": influence_breakdown,
            "decision_influence": {
                "level": influence,
                "provenance": influence_provenance,
                "established_count": len(memories_used),
                "hypothesis_count": len(hyp_list),
                "hypothesis_influence_detected": any(
                    ib.get("influence", "none") != "none"
                    for ib in influence_breakdown.values()
                    if ib.get("type") == "hypothesis"
                ),
            },
            "memory_summary": f"Retrieved {len(memories_used)} memories, {len(hyp_list)} hypotheses (separated). Memory is supporting input only.",
        },

        "skill": {
            "lead_skill": lead_skill,
            "lead_loaded": lead_skill_loaded,
            "support_skills": support_skills_loaded,
            "skills_loaded": skills_loaded,
            "source": "skill_loader.build_skill_context() — Phase 5.7 REAL Skill Loader",
        },

        "orchestrator": {
            "team_formed": not single_agent,
            "team_size": team_size,
            "lead_role": lead_skill,
            "support_roles": support_skills_loaded,
        },

        "agent_invocation": {
            "backend": provider,
            "model": model,
            "session_id": runtime_result.get("session_id", ""),
            "tokens": runtime_result.get("tokens", {"total": 0, "input": 0, "output": 0}),
            "cost": runtime_result.get("cost", 0),
            "latency_ms": runtime_result.get("latency_ms", 0),
        },

        "agent_response": runtime_result.get("response_text", ""),

        # P0-1: Execution reliability
        "execution_reliability": reliability_info,

        # P0-2: Cross-stack validation
        "cross_stack_validation": cross_stack_info,

        "code_validation": {},

        "pipeline_stages": {
            "router": {"status": "completed", "started_at": ts.get("routing_completed", now), "completed_at": ts.get("routing_completed", now)},
            "memory": {"status": "completed" if decision_context.get("retrieved") else "skipped", "started_at": ts.get("memory_retrieved", now), "completed_at": ts.get("memory_retrieved", now)},
            "skill": {"status": "completed", "started_at": ts.get("skill_loaded", now), "completed_at": ts.get("skill_loaded", now)},
            "orchestrator": {"status": "completed", "started_at": ts.get("orchestration_completed", now), "completed_at": ts.get("orchestration_completed", now)},
            "runtime": {"status": "completed", "started_at": ts.get("agent_started", now), "completed_at": ts.get("agent_completed", now)},
            "trace": {"status": "completed"},
        },

        "decision_provenance": {
            "router_rules": rules_applied,
            "memory_match_reasons": {
                m["memory_id"]: m.get("match_reasons", [])
                for m in memories_considered
            },
            "orchestrator_rules": ["single_skill" if single_agent else "multi_skill"],
        },
    }

    return trace


# ── Legacy compatibility wrapper ─────────────────────────────────

def execute(task_id, task_text, decision_context, model="", provider="opencode",
            pipeline_timestamps=None, project_root=""):
    """
    Execute a task via the runtime provider.
    Legacy wrapper — use execute_with_reliability for P0-1 features.

    This is the function called by loop_controller.py.
    """
    exec_result = execute_with_reliability(
        task_id=task_id,
        task_text=task_text,
        decision_context=decision_context,
        model=model,
        provider=provider,
        project_root=project_root,
    )

    execution_id = generate_execution_id()
    trace_id = generate_trace_id(execution_id)

    if pipeline_timestamps is None:
        pipeline_timestamps = {}

    # Build trace
    trace = build_trace(
        execution_id, trace_id, task_id, task_text, decision_context,
        provider, model, exec_result, pipeline_timestamps=pipeline_timestamps,
    )

    # Write trace file — Phase 5.9: atomic write
    trace_file = os.path.join(TRACES_DIR, f"{execution_id}.yaml")
    header_lines = [
        f"# Execution Trace — {task_id} (Memory {'ON' if decision_context.get('retrieved') else 'OFF'})",
        f"# Phase 5.7 — Agent OS Runtime Pipeline (Closed Loop)",
        f"# Generated: {datetime.now(timezone.utc).isoformat()}",
        f"# Provider: {provider}",
        f"# Model: {model}",
    ]
    atomic_yaml_write(trace_file, trace, header_lines=header_lines)

    return {
        "execution_id": execution_id,
        "trace_id": trace_id,
        "trace_file": trace_file,
        "session_id": exec_result.get("session_id", ""),
        "latency_ms": exec_result.get("latency_ms", 0),
        "token_usage": exec_result.get("tokens", {"total": 0, "input": 0, "output": 0}),
        "output_hash": compute_output_hash(exec_result.get("response_text", "")),
        "status": exec_result.get("status", "error"),
        "error": exec_result.get("error", ""),
        "reliability": exec_result.get("reliability", {}),
        "cross_stack_warning": exec_result.get("cross_stack_warning", {}),
    }