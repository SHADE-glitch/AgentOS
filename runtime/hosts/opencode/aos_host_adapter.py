#!/usr/bin/env python3
"""
AOS Host Adapter — Phase 6.0.2

Provides decision context to OpenCode Host via the plugin system.

Pipeline:
  OpenCode Plugin
    ↓ (task context)
  AOS Host Adapter
    ↓ (calls existing AOS components)
  Router / Memory / Orchestrator
    ↓ (decision context)
  OpenCode Plugin
    ↓ (injects into system prompt)
  OpenCode Model

CRITICAL CONSTRAINTS:
  - Does NOT call runtime_adapter (would cause recursion)
  - Does NOT start new OpenCode instances
  - Does NOT duplicate Router/Memory/Orchestrator logic
  - Only CALLS existing components and returns context
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

# ── Path Setup ────────────────────────────────────────────────────
BASE = "/home/shade/.agents"
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "retrieval"))
sys.path.insert(0, os.path.join(BASE, "runtime", "loop-controller"))

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


def _generate_instructions(
    task_text: str,
    classification: dict,
    memory: dict,
    orchestration: dict,
) -> list:
    """Generate contextual instructions for the model."""
    instructions = []

    # Role-based instruction
    lead = orchestration.get("lead_agent", "general")
    if lead != "general":
        instructions.append(f"Act as {lead} for this task.")

    # Memory-based instruction
    memories = memory.get("memories", [])
    if memories:
        relevant_ids = [m.get("memory_id", "") for m in memories[:3]]
        instructions.append(f"Consider past decisions: {', '.join(relevant_ids)}")

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


# ── CLI Interface ─────────────────────────────────────────────────
def main():
    """CLI entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="AOS Host Adapter")
    parser.add_argument("task", help="Task description")
    parser.add_argument("--session", default="", help="Session ID")
    parser.add_argument("--cwd", default="", help="Working directory")
    parser.add_argument("--model", default="", help="Model name")
    parser.add_argument("--provider", default="", help="Provider name")
    parser.add_argument("--memory", default="enabled", help="Memory mode")
    parser.add_argument("--task-id", default="", help="Task ID from plugin (for correlation)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

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
