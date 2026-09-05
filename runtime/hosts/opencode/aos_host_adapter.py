#!/usr/bin/env python3
"""
AOS Host Adapter — Phase 15 (Runtime Integration Repair)

Provides decision context AND runtime entry to OpenCode Host via the plugin system.

Two modes:
  1. Advisory (default): Returns decision context for prompt injection
  2. Runtime (--runtime): Invokes loop_controller for full pipeline execution

Pipeline (advisory):
  OpenCode Plugin
    ↓ (task context)
  AOS Host Adapter
    ↓ (calls existing AOS components)
  Router / Memory / Orchestrator
    ↓ (decision context)
  OpenCode Plugin
    ↓ (injects into system prompt)
  OpenCode Model

Pipeline (runtime):
  OpenCode Plugin / CLI
    ↓ (task context)
  AOS Host Adapter
    ↓ (invokes loop_controller with host_delegate provider)
  loop_controller → retrieval → HybridRouter → skill → evidence → loop state
    ↓ (returns governance context)
  OpenCode Plugin / CLI

CRITICAL CONSTRAINTS:
  - Runtime mode uses host_delegate provider (no recursive opencode run)
  - Does NOT start new OpenCode instances
  - Does NOT duplicate Router/Memory/Orchestrator logic
  - Only CALLS existing components and returns context
"""

import os
import sys
import json
import uuid
import subprocess
from datetime import datetime, timezone

# ── Path Setup ────────────────────────────────────────────────────
BASE = "/home/shade/.agents"
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "retrieval"))
sys.path.insert(0, os.path.join(BASE, "runtime", "loop-controller"))

LOOP_CONTROLLER = os.path.join(BASE, "runtime", "loop-controller", "loop_controller.py")

# ── Recursion Guard ───────────────────────────────────────────────
# If AOS_HOST_ADAPTER is already set, we're in recursion — abort
RECURSION_GUARD = "AOS_HOST_ADAPTER_ACTIVE"

def check_recursion():
    """Prevent recursive AOS calls from OpenCode Host."""
    if os.environ.get(RECURSION_GUARD):
        return True
    os.environ[RECURSION_GUARD] = "1"
    return False

def clear_recursion():
    """Clear recursion guard after completion."""
    os.environ.pop(RECURSION_GUARD, None)


# ── Import AOS Components (lazy to avoid circular imports) ────────
def _import_retrieval():
    """Import retrieval adapter."""
    from retrieval_adapter import adapt as retrieval_adapt, classify_task
    return retrieval_adapt, classify_task

def _import_orchestrator():
    """Import orchestrator logic if available."""
    try:
        from orchestrator import form_team
        return form_team
    except ImportError:
        return None


# ── Host Adapter Interface ────────────────────────────────────────
def get_decision_context(
    task_text: str,
    session_id: str = "",
    working_directory: str = "",
    model: str = "",
    provider: str = "",
    memory_mode: str = "enabled",
    task_id: str = "",
) -> dict:
    """
    Get AOS decision context for a task.

    This is the main entry point called by the OpenCode plugin.

    Returns:
        dict with decision context to inject into system prompt
    """
    # Recursion protection
    if check_recursion():
        return _fallback_context(task_text, "recursion_detected")

    try:
        task_id = task_id if task_id else f"HOST-{uuid.uuid4().hex[:6].upper()}"

        context = {
            "task_id": task_id,
            "task_text": task_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "working_directory": working_directory,
            "runtime": {
                "provider": provider,
                "model": model,
            },
            "aos_status": "unavailable",
            "decision": {},
            "memory": {},
            "orchestration": {},
            "warnings": [],
            "instructions": [],
        }

        # Stage 1: Memory Retrieval
        try:
            retrieval_adapt, classify_task = _import_retrieval()
            decision_context = retrieval_adapt(task_id, task_text, memory_mode)
            context["memory"] = {
                "retrieved": decision_context.get("total_retrieved", 0),
                "memories": decision_context.get("memories", []),
                "hypotheses": decision_context.get("hypotheses", []),
                "ranking": decision_context.get("ranking", []),
            }
            context["aos_status"] = "memory_retrieved"
        except Exception as e:
            context["memory"] = {"error": str(e), "retrieved": 0}

        # Stage 2: Task Classification
        try:
            _, classify_task = _import_retrieval()
            classification = classify_task(task_text)
            context["decision"]["classification"] = classification
            context["aos_status"] = "classified"
        except Exception as e:
            context["decision"]["classification"] = {
                "category": "unknown",
                "domains": [],
                "roles": [],
                "keywords": [],
                "difficulty": "medium",
            }

        # Stage 3: Routing (via existing router rules)
        try:
            classification = context["decision"].get("classification", {})
            roles = classification.get("roles", [])
            if roles:
                context["orchestration"]["lead_agent"] = roles[0]
                context["orchestration"]["support_agents"] = roles[1:] if len(roles) > 1 else []
            else:
                context["orchestration"]["lead_agent"] = _infer_role(task_text)
                context["orchestration"]["support_agents"] = []
            context["aos_status"] = "routed"
        except Exception as e:
            context["orchestration"]["lead_agent"] = "general"
            context["orchestration"]["support_agents"] = []

        # Stage 4: Generate Instructions
        context["instructions"] = _generate_instructions(
            task_text,
            context["decision"].get("classification", {}),
            context["memory"],
            context["orchestration"],
        )

        # Stage 5: Warnings
        context["warnings"] = _generate_warnings(task_text, context)

        context["aos_status"] = "completed"
        return context

    except Exception as e:
        return _fallback_context(task_text, f"adapter_error: {e}")
    finally:
        clear_recursion()


def _fallback_context(task_text: str, reason: str) -> dict:
    """Return minimal context when AOS is unavailable."""
    return {
        "task_id": f"FALLBACK-{uuid.uuid4().hex[:6].upper()}",
        "task_text": task_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aos_status": "fallback",
        "fallback_reason": reason,
        "decision": {},
        "memory": {},
        "orchestration": {"lead_agent": "general"},
        "warnings": [],
        "instructions": [],
    }


def _infer_role(task_text: str) -> str:
    """Simple role inference from task text keywords."""
    task_lower = task_text.lower()

    role_keywords = {
        "security-engineer": ["security", "auth", "jwt", "token", "password", "加密", "认证", "安全"],
        "database-engineer": ["mysql", "postgres", "sql", "database", "索引", "查询", "数据库"],
        "backend-architect": ["api", "microservice", "spring", "backend", "后端", "接口"],
        "frontend-architect": ["react", "vue", "css", "ui", "frontend", "前端", "组件"],
        "devops-engineer": ["docker", "kubernetes", "deploy", "ci/cd", "部署", "运维"],
        "rag-engineer": ["rag", "embedding", "vector", "检索", "向量"],
        "testing-engineer": ["test", "qa", "coverage", "测试", "用例"],
    }

    for role, keywords in role_keywords.items():
        if any(kw in task_lower for kw in keywords):
            return role

    return "general"


# ── Memory Guidance Templates (Phase 8.2.1.4) ────────────────────
# Maps memory type to guidance framing for semantic injection.
# Each template must include: {memory_id}, {evidence}, {success_rate}.

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

# Top-N memories to inject (configurable)
_MEMORY_INJECTION_LIMIT = 5


def _format_memory_guidance(memory: dict, rank: int) -> str:
    """Format a single memory as semantic decision guidance.

    Produces a structured guidance line that includes:
      - memory_id (provenance)
      - type label and evidence_level (credibility)
      - success_rate (reliability)
      - category and tags (domain context)
      - generated guidance (actionable direction)
      - recommended action (what to do with this memory)

    Args:
        memory: dict from retrieval adapter with memory_id, type, evidence_level,
                success_rate, category, tags, confidence_score, etc.
        rank: 1-based rank in the retrieval results.

    Returns:
        Formatted guidance string.
    """
    mid = memory.get("memory_id", "?")
    mtype = memory.get("type", "memory")
    evidence = memory.get("evidence_level", "unknown")
    success_rate = memory.get("success_rate", 0.0)
    category = memory.get("category", "unknown")
    tags = memory.get("tags", [])
    confidence = memory.get("confidence", "low")
    score = memory.get("final_score", 0.0)

    # Credibility label
    evidence_icon = _evidence_icon(evidence)
    credibility = _evidence_label(evidence, success_rate)

    # Tags string (limit to 5)
    tag_str = ", ".join(tags[:5]) if tags else "none"

    # Guidance from type
    guidance = _TYPE_GUIDANCE_TEMPLATES.get(mtype, _TYPE_GUIDANCE_TEMPLATES["task"])

    # Recommended action
    action = _TYPE_ACTION_TEMPLATES.get(mtype, _TYPE_ACTION_TEMPLATES["task"])

    # Hypothesis warning
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


def _generate_instructions(
    task_text: str,
    classification: dict,
    memory: dict,
    orchestration: dict,
) -> list:
    """Generate contextual instructions for the model.

    Phase 8.2.1.4: Semantic injection replaces ID-only injection.
    Each retrieved memory is formatted as structured decision guidance
    including evidence level, success rate, category, tags, and actionable
    direction.
    """
    instructions = []

    # Role-based instruction
    lead = orchestration.get("lead_agent", "general")
    if lead != "general":
        instructions.append(f"Act as {lead} for this task.")

    # ── Phase 8.2.1.4: Semantic Memory Injection ──────────────────
    memories = memory.get("memories", [])
    hypotheses = memory.get("hypotheses", [])

    if memories:
        # Established memories: inject as structured guidance
        guidance_lines = ["[RELEVANT MEMORY — Decision Guidance]"]
        for i, mem in enumerate(memories[:_MEMORY_INJECTION_LIMIT]):
            guidance_lines.append(_format_memory_guidance(mem, i + 1))
        instructions.append("\n".join(guidance_lines))

        # Track injected memory IDs for telemetry
        memory["injected_ids"] = [m.get("memory_id") for m in memories[:_MEMORY_INJECTION_LIMIT]]
        memory["injected_count"] = len(memory["injected_ids"])
        memory["injection_format"] = "semantic_guidance"
    else:
        memory["injected_ids"] = []
        memory["injected_count"] = 0
        memory["injection_format"] = "none"

    if hypotheses:
        # Hypotheses: inject separately with [UNVALIDATED] prefix
        hyp_lines = ["[HYPOTHESES — Unvalidated, test before relying]"]
        for i, hyp in enumerate(hypotheses[:_MEMORY_INJECTION_LIMIT]):
            hyp_lines.append(_format_memory_guidance(hyp, i + 1))
        instructions.append("\n".join(hyp_lines))

        memory["injected_hypothesis_ids"] = [h.get("memory_id") for h in hypotheses[:_MEMORY_INJECTION_LIMIT]]
        memory["injected_hypothesis_count"] = len(memory["injected_hypothesis_ids"])
    else:
        memory["injected_hypothesis_ids"] = []
        memory["injected_hypothesis_count"] = 0

    # Classification-based instruction
    difficulty = classification.get("difficulty", "medium")
    if difficulty == "high":
        instructions.append("This is a complex task. Break it into steps.")
    elif difficulty == "low":
        instructions.append("This is a straightforward task.")

    return instructions


def _generate_warnings(task_text: str, context: dict) -> list:
    """Generate safety warnings."""
    warnings = []

    task_lower = task_text.lower()

    # Security warnings
    if any(kw in task_lower for kw in ["delete", "drop", "remove", "删除", "drop"]):
        warnings.append("DESTRUCTIVE_ACTION: This task may involve data deletion.")

    if any(kw in task_lower for kw in ["password", "secret", "key", "token", "密码", "密钥"]):
        warnings.append("SENSITIVE_DATA: This task involves sensitive credentials.")

    if any(kw in task_lower for kw in ["git push", "merge", "deploy", "发布"]):
        warnings.append("IRREVERSIBLE_ACTION: This task may affect remote systems.")

    return warnings


# ── Runtime Entry (Phase 15) ──────────────────────────────────────
def invoke_loop_controller(
    task_text: str,
    session_id: str = "",
    working_directory: str = "",
    model: str = "",
    provider: str = "host_delegate",
    memory_mode: str = "enabled",
    task_id: str = "",
) -> dict:
    """
    Invoke the loop_controller for full runtime entry.

    Uses host_delegate provider to avoid spawning recursive opencode run.
    The loop_controller runs: retrieval → HybridRouter → skill → evidence → loop state.
    Returns governance context with loop_id, session_id, router decision, etc.
    """
    import uuid as _uuid

    task_id = task_id if task_id else f"HOST-{_uuid.uuid4().hex[:6].upper()}"
    session_id = session_id or datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S")

    cmd = [
        sys.executable,
        LOOP_CONTROLLER,
        task_id,
        task_text,
        memory_mode,
        model,
        provider,
        "HOST_DELEGATED",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=working_directory or os.getcwd(),
            env={
                **os.environ,
                "AGENT_OS_ROOT": BASE,
                "AOS_SESSION_ID": session_id,
                "AOS_HOST_PLUGIN_ACTIVE": "1",
            },
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Extract loop_id from stdout
        import re
        loop_id = ""
        m = re.search(r"Loop ID:\s*(LOOP-\S+)", result.stdout)
        if m:
            loop_id = m.group(1)

        return {
            "task_id": task_id,
            "loop_id": loop_id,
            "session_id": session_id,
            "aos_status": "completed" if result.returncode == 0 else "error",
            "exit_code": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[:500] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "task_id": task_id,
            "loop_id": "",
            "session_id": session_id,
            "aos_status": "timeout",
            "exit_code": -1,
            "stdout": "",
            "stderr": "Loop controller timed out after 60s",
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "loop_id": "",
            "session_id": session_id,
            "aos_status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
        }


# ── CLI Interface ─────────────────────────────────────────────────
def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="AOS Host Adapter")
    parser.add_argument("task", nargs="?", help="Task description")
    parser.add_argument("--session", default="", help="Session ID")
    parser.add_argument("--cwd", default="", help="Working directory")
    parser.add_argument("--model", default="", help="Model name")
    parser.add_argument("--provider", default="", help="Provider name")
    parser.add_argument("--memory", default="enabled", help="Memory mode")
    parser.add_argument("--task-id", default="", help="Task ID from plugin (for correlation)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--runtime", action="store_true", help="Invoke loop_controller for full runtime entry")

    args = parser.parse_args()

    if args.runtime:
        if not args.task:
            print("Error: --runtime requires a task description", file=sys.stderr)
            sys.exit(1)
        result = invoke_loop_controller(
            task_text=args.task,
            session_id=args.session,
            working_directory=args.cwd,
            model=args.model,
            provider=args.provider or "host_delegate",
            memory_mode=args.memory,
            task_id=args.task_id,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"AOS Status:   {result['aos_status']}")
            print(f"Task ID:      {result['task_id']}")
            print(f"Loop ID:      {result.get('loop_id', '?')}")
            print(f"Session ID:   {result.get('session_id', '?')}")
        sys.exit(0 if result["aos_status"] == "completed" else 1)

    if not args.task:
        print("Error: task description required", file=sys.stderr)
        sys.exit(1)

    context = get_decision_context(
        task_text=args.task,
        session_id=args.session,
        working_directory=args.cwd,
        model=args.model,
        provider=args.provider,
        memory_mode=args.memory,
        task_id=args.task_id,
    )

    if args.json:
        print(json.dumps(context, indent=2, ensure_ascii=False))
    else:
        print(f"AOS Status:   {context['aos_status']}")
        print(f"Task ID:      {context['task_id']}")
        print(f"Lead Agent:   {context['orchestration'].get('lead_agent', '?')}")
        print(f"Memory:       {context['memory'].get('retrieved', 0)} memories")
        print(f"Warnings:     {len(context['warnings'])}")
        print(f"Instructions: {len(context['instructions'])}")
        if context['warnings']:
            for w in context['warnings']:
                print(f"  ⚠ {w}")
        if context['instructions']:
            for i in context['instructions']:
                print(f"  → {i}")


if __name__ == "__main__":
    main()
