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


def build_prompt(task_text, decision_context, project_root=""):
    """
    Construct the prompt for the runtime provider.
    Memory is included as SUPPORTING context only.
    Stack context is included (P0-2).
    Phase 5.7: Skill context is included from real Skill Loader.

    The prompt tells the model to act as the appropriate role based on
    task classification. Memory is presented as "prior experience" that
    the model MAY use but MUST NOT blindly follow.

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

    # Memory context (supporting only)
    if mem or hyp:
        parts.append("## Prior Experience (use only if relevant)")
        parts.append("The following is prior experience from similar tasks. ")
        parts.append("It is supporting information only — do NOT blindly follow it.")
        parts.append("Apply your own judgment based on the actual task requirements.")
        parts.append("")

        if mem:
            parts.append("### Established Patterns")
            for m in mem:
                mid = m.get("memory_id", "?")
                mtype = m.get("type", "?")
                cat = m.get("category", "?")
                score = m.get("final_score", 0)
                reasons = m.get("match_reasons", [])
                evidence = m.get("evidence_level", "?")
                parts.append(f"- **{mid}** ({mtype}, {cat})")
                parts.append(f"  Relevance: {score:.2f}, Evidence: {evidence}")
                if reasons:
                    parts.append(f"  Matched: {', '.join(reasons)}")
                if m.get("warning"):
                    parts.append(f"  Warning: {m['warning']}")
                parts.append("")

        if hyp:
            parts.append("### Hypotheses (unvalidated — treat with caution)")
            for h in hyp:
                hid = h.get("memory_id", "?")
                parts.append(f"- **{hid}** — UNVALIDATED. Do not treat as fact.")
                parts.append("")

    # Task
    parts.append("## Task")
    parts.append(task_text)
    parts.append("")
    parts.append("Provide a thorough, structured response. Include specific steps, code examples, or configuration recommendations as appropriate.")

    return "\n".join(parts)


# ── Provider Invocation ──────────────────────────────────────────

def _invoke_opencode_provider(prompt, model, timeout_seconds=300):
    """OpenCode provider: call opencode CLI and parse JSONL output."""
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


def invoke_runtime(provider, prompt, model, timeout_seconds=300):
    """
    Dispatch to the appropriate runtime provider.

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
                             reliability_config=None):
    """
    Execute a task with reliability guard (P0-1).

    Features:
      - Retry with exponential backoff on REAL_AGENT_FAILURE
      - Model fallback chain
      - Early termination on RETRY_STORM or ORCHESTRATION_FAILURE
      - Failure classification and tracking

    Args:
        task_id: str
        task_text: str
        decision_context: dict from retrieval adapter
        model: str, primary model
        provider: str, runtime provider
        project_root: str, project root for stack detection (P0-2)
        reliability_config: ReliabilityConfig or None (uses defaults)

    Returns:
        dict: execution result with reliability summary
    """
    if reliability_config is None:
        reliability_config = create_default_config()

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

    # Determine influence
    if not memories_used:
        influence = "none"
    elif len(memories_used) == 1 and mem_list[0].get("memory_id", "").startswith("AP-"):
        influence = "confirmation"
    else:
        influence = "confirmation"

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
            "influence": influence,
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