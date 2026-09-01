#!/usr/bin/env python3
"""
Agent Router — Phase 7.1

Thin backward-compatibility wrapper delegating to runtime/router/router.py.
All routing rules are now in runtime/router/rules.yaml.

The Router Runtime is the canonical implementation.
This file is kept for backward compatibility — loop_controller.py
imports `from agent_router import route as router_route`.
"""

import os
import sys
from datetime import datetime, timezone

BASE = "/home/shade/.agents"

# Import the canonical Router Runtime
sys.path.insert(0, os.path.join(BASE, "runtime", "router"))
from router import Router, get_router

# Lazy singleton — initialized on first call
_router = None


def _ensure_router():
    global _router
    if _router is None:
        _router = get_router()
    return _router


def classify_intent(task_text: str) -> dict:
    """
    Classify task intent and domains.
    Delegates to Router Runtime.
    """
    router = _ensure_router()
    c = router.classify(task_text)
    return {
        "intent": c.category,
        "domains": c.domains,
    }


def route(task_text: str, memory_context: dict = None) -> dict:
    """
    Route a task to the appropriate skill(s).

    This is the backward-compatible wrapper. It delegates to the
    canonical Router Runtime (runtime/router/router.py).

    Args:
        task_text: The task description
        memory_context: Optional dict with memories that may influence routing

    Returns:
        dict: RouteDecision (backward-compatible shape)
    """
    router = _ensure_router()
    decision = router.route(task_text, memory_context=memory_context)

    return {
        "intent": decision.intent,
        "domains": decision.domains,
        "primary_domain": decision.primary_domain,
        "lead_skill": decision.lead_skill,
        "support_skills": decision.support_skills,
        "confidence": decision.confidence,
        "memory_influence": decision.memory_influence,
        "memory_retrieved": decision.memory_retrieved,
        "rules_applied": decision.rules_applied,
        "started_at": decision.started_at,
        "completed_at": decision.completed_at,
    }