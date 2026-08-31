#!/usr/bin/env python3
"""
Runtime Adapter — Phase 5.10.3 (Runtime Neutralization)
Bridges DecisionContext → Runtime Provider → Trace.

DecisionContext + Task → Runtime Provider Abstraction → trace YAML

This adapter:
  1. Constructs a prompt with memory context as SUPPORTING input
  2. Dispatches to the appropriate runtime provider via invoke_runtime()
  3. Parses provider output (session_id, tokens, response, latency)
  4. Writes a trace file to runtime/traces/
  5. Returns ExecutionResult

Provider abstraction: Agent OS core never references a specific runtime.
Providers are resolved via the runtime contract.
"""

import subprocess
import json
import yaml
import os
import hashlib
import time
import uuid
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
TRACES_DIR = os.path.join(BASE, "runtime", "traces")

# Defaults — sourced from environment, host, or CLI (never hardcoded)
DEFAULT_PROVIDER = os.environ.get("AOS_RUNTIME_PROVIDER", "opencode")
DEFAULT_MODEL = os.environ.get("AOS_RUNTIME_MODEL", "")

# Timeout for provider CLI
TIMEOUT_SECONDS = 300


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


def build_prompt(task_text, decision_context):
    """
    Construct the prompt for the runtime provider.
    Memory is included as SUPPORTING context only.

    The prompt tells the model to act as the appropriate role based on
    task classification. Memory is presented as "prior experience" that
    the model MAY use but MUST NOT blindly follow.
    """
    mem = decision_context.get("memories", [])
    hyp = decision_context.get("hypotheses", [])
    classification = decision_context.get("classification", {})

    category = classification.get("category", "backend")
    domains = classification.get("domains", [])
    domain_str = ", ".join(domains) if domains else "general"

    parts = []

    # System context
    parts.append(f"You are an expert software engineer working on a {category} task.")
    parts.append(f"Domain: {domain_str}")
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

def _invoke_opencode_provider(prompt, model):
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
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "session_id": "",
            "response_text": "",
            "tokens": {"total": 0, "input": 0, "output": 0},
            "cost": 0,
            "latency_ms": int(TIMEOUT_SECONDS * 1000),
            "status": "timeout",
            "error": f"opencode run exceeded {TIMEOUT_SECONDS}s timeout",
            "provider": "opencode",
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
        }

    return {
        "session_id": session_id,
        "response_text": response_text,
        "tokens": tokens,
        "cost": cost,
        "latency_ms": latency_ms,
        "status": "success",
        "provider": "opencode",
    }


# Provider dispatch table
PROVIDER_DISPATCH = {
    "opencode": _invoke_opencode_provider,
}


def invoke_runtime(provider, prompt, model):
    """
    Dispatch to the appropriate runtime provider.

    Args:
        provider: str, provider name (opencode, ...)
        prompt: str, the constructed prompt
        model: str, provider-specific model identifier

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
        }
    return invoke_fn(prompt, model)


# ── Trace Building ───────────────────────────────────────────────

def build_trace(execution_id, trace_id, task_id, task_text, decision_context,
                provider, model, runtime_result, pipeline_timestamps=None):
    """
    Build a trace YAML dict. Provider-agnostic.

    pipeline_timestamps: dict with keys:
        task_received, routing_completed, memory_retrieved,
        orchestration_completed, agent_started, agent_completed
    """
    now = datetime.now(timezone.utc).isoformat()
    classification = decision_context.get("classification", {})

    if pipeline_timestamps is None:
        pipeline_timestamps = {}

    ts = pipeline_timestamps

    # Memory retrieval section
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

    # Router section (derived from classification + memory)
    category = classification.get("category", "backend")
    domains = classification.get("domains", [])
    roles = classification.get("roles", [])

    # Lead agent from classification; fallback based on category
    lead_agent = roles[0] if roles else f"{category}-engineer"
    intent_map = {
        "optimization": "Optimization",
        "backend": "Backend Development",
        "frontend": "Frontend Development",
        "architecture": "Architecture Design",
        "ai": "AI/ML Engineering",
        "database": "Database Engineering",
        "devops": "DevOps",
    }
    intent = intent_map.get(category, "General Engineering")

    # Orchestrator section
    single_agent = len(domains) <= 1 and len(roles) <= 2
    anti_pattern = single_agent and len(memories_used) > 0

    trace = {
        "execution_id": execution_id,
        "trace_id": trace_id,
        "task_id": task_id,
        "task_text": task_text,
        "domain": category.capitalize(),
        "difficulty": classification.get("difficulty", "medium"),
        "memory_mode": "on" if decision_context.get("retrieved") else "off",
        "provider": provider,
        "model": model,
        "status": runtime_result["status"],

        "pipeline": {
            "step_timestamps": {
                "task_received": ts.get("task_received", now),
                "routing_completed": ts.get("routing_completed", now),
                "memory_retrieved": ts.get("memory_retrieved", now),
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
            "lead_agent": lead_agent,
            "support_agents": roles[1:] if len(roles) > 1 else [],
            "confidence": "high" if domains else "medium",
            "reason": f"Task classification: {category}, domains={domains}",
            "rules_applied": [f"Category {category} → {lead_agent}"],
        },

        "memory_retrieval": {
            "mode": "on" if decision_context.get("retrieved") else "off",
            "total_retrieved": len(memories_considered),
            "memories_considered": memories_considered,
            "memories_used": memories_used,
            "influence": influence,
            "memory_summary": f"Retrieved {len(memories_used)} memories, {len(hyp_list)} hypotheses (separated). Memory is supporting input only.",
        },

        "orchestrator": {
            "team_formed": not single_agent,
            "team_size": len(roles) if not single_agent else 1,
            "lead_role": lead_agent,
            "support_roles": roles[1:] if len(roles) > 1 else [],
            "anti_pattern_alert": anti_pattern,
            "anti_pattern_id": "AP-001" if anti_pattern else None,
            "anti_pattern_detail": "Team Inflation Guard: single-domain task should not form a team" if anti_pattern else None,
            "reason": f"domains={len(domains)}, roles={len(roles)}. {'Single-agent' if single_agent else 'Multi-agent'} mode.",
            "rules_applied": [
                f"R1: domains={len(domains)} → {'single-agent' if len(domains) <= 1 else 'multi-agent'} candidate",
                f"R2: roles={len(roles)} → {'no team needed' if len(roles) <= 2 else 'team appropriate'}",
            ],
        },

        "agent_invocation": {
            "provider": provider,
            "cli_command": f"{provider} run --format json --auto --model {model} '<prompt>'",
            "session_id": runtime_result.get("session_id", ""),
            "model": model,
            "tokens": runtime_result.get("tokens", {}),
            "cost": runtime_result.get("cost", 0),
            "latency_ms": runtime_result.get("latency_ms", 0),
        },

        "agent_response": runtime_result.get("response_text", ""),

        "decision_provenance": {
            "router_rules": [f"Category {category} → {lead_agent}"],
            "memory_match_reasons": {
                m["memory_id"]: m.get("match_reasons", [])
                for m in mem_list
            },
            "orchestrator_rules": [
                f"R1: domains={len(domains)}",
                f"R2: roles={len(roles)}",
            ],
        },

        "evidence": {
            "level": "Level 2 — Runtime Validated",
            "description": f"Real model invocation through {provider} CLI. Generated by loop-controller runtime_adapter.",
            "is_real_execution": True,
            "is_ai_generated_yaml": False,
            "verification": [
                f"Router: classification → {lead_agent}",
                f"Memory: retrieval_adapter → {len(memories_used)} memories, {len(hyp_list)} hypotheses",
                f"Orchestrator: domains={len(domains)} → {'single-agent' if single_agent else 'multi-agent'}",
                f"Agent: {provider} run invoked with session {runtime_result.get('session_id', '?')}",
                f"Response: {len(runtime_result.get('response_text', ''))} chars",
                f"Tokens: {runtime_result.get('tokens', {}).get('total', 0)} total, cost={runtime_result.get('cost', 0)}",
            ],
        },
    }

    return trace


# ── Main Execute ─────────────────────────────────────────────────

def execute(task_id, task_text, decision_context, model="", provider="opencode",
            pipeline_timestamps=None):
    """
    Execute a task through the runtime provider abstraction.

    Args:
        task_id: str like "RT-003"
        task_text: str, the task description
        decision_context: dict from retrieval_adapter.adapt()
        model: str, provider-specific model identifier
        provider: str, provider name (opencode, ...)
        pipeline_timestamps: dict with real timestamps from loop controller

    Returns:
        ExecutionResult dict with execution_id, trace_id, session_id, etc.
    """
    execution_id = generate_execution_id()
    trace_id = generate_trace_id(execution_id)

    if pipeline_timestamps is None:
        pipeline_timestamps = {}

    print(f"[runtime_adapter] execution_id={execution_id}")
    print(f"[runtime_adapter] trace_id={trace_id}")
    print(f"[runtime_adapter] provider={provider}")
    print(f"[runtime_adapter] model={model}")

    # Build prompt
    prompt = build_prompt(task_text, decision_context)
    print(f"[runtime_adapter] prompt_length={len(prompt)} chars")

    # Record agent start time
    agent_started = datetime.now(timezone.utc).isoformat()
    pipeline_timestamps["agent_started"] = agent_started

    # Invoke runtime provider
    print(f"[runtime_adapter] invoking {provider} run...")
    runtime_result = invoke_runtime(provider, prompt, model)

    # Record agent completion time
    agent_completed = datetime.now(timezone.utc).isoformat()
    pipeline_timestamps["agent_completed"] = agent_completed

    print(f"[runtime_adapter] status={runtime_result['status']}")
    print(f"[runtime_adapter] session_id={runtime_result.get('session_id', '?')}")
    print(f"[runtime_adapter] tokens={runtime_result.get('tokens', {}).get('total', 0)}")
    print(f"[runtime_adapter] latency_ms={runtime_result.get('latency_ms', 0)}")
    print(f"[runtime_adapter] response_length={len(runtime_result.get('response_text', ''))} chars")

    # Build trace
    trace = build_trace(
        execution_id, trace_id, task_id, task_text,
        decision_context, provider, model, runtime_result,
        pipeline_timestamps=pipeline_timestamps,
    )

    # Write trace file
    os.makedirs(TRACES_DIR, exist_ok=True)
    trace_path = os.path.join(TRACES_DIR, f"{execution_id}.yaml")
    with open(trace_path, "w") as f:
        f.write(f"# Execution Trace — {task_id} (Memory {'ON' if decision_context.get('retrieved') else 'OFF'})\n")
        f.write(f"# Phase 5.10.3 — Runtime Neutralization\n")
        f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Provider: {provider}\n")
        f.write("\n")
        yaml.dump(trace, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"[runtime_adapter] trace written to {trace_path}")

    return {
        "execution_id": execution_id,
        "trace_id": trace_id,
        "session_id": runtime_result.get("session_id", ""),
        "provider": provider,
        "model": model,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "latency_ms": runtime_result.get("latency_ms", 0),
        "token_usage": runtime_result.get("tokens", {}),
        "output_hash": compute_output_hash(runtime_result.get("response_text", "")),
        "final_output": runtime_result.get("response_text", ""),
        "status": runtime_result["status"],
        "trace_file": trace_path,
        "error": runtime_result.get("error", ""),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 runtime_adapter.py <task_id> <task_text> [provider] [model]")
        print("Example: python3 runtime_adapter.py RT-003 'Analyze MySQL slow queries' opencode opencode/mimo-v2.5-free")
        sys.exit(1)

    task_id = sys.argv[1]
    task_text = sys.argv[2]
    provider = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_PROVIDER
    model = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_MODEL

    # For standalone CLI, create a minimal decision_context
    decision_context = {
        "retrieved": False,
        "memories": [],
        "hypotheses": [],
        "total_retrieved": 0,
        "ranking": [],
        "classification": {},
        "entry_metadata": {},
    }

    result = execute(task_id, task_text, decision_context, model=model, provider=provider)
    print(f"\nResult: {result['status']}")
    print(f"Execution: {result['execution_id']}")
    print(f"Trace: {result['trace_id']}")
    print(f"Session: {result['session_id']}")
    print(f"Provider: {result['provider']}")
    print(f"Model: {result['model']}")