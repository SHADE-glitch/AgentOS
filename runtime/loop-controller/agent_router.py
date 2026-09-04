#!/usr/bin/env python3
"""
Agent Router — Phase14

Thin backward-compatibility wrapper delegating to HybridRouter
(runtime/router/hybrid_router.py). Phase14 Repair: wires the HybridRouter
into the formal runtime call chain, replacing the Phase13.1 Router.

The HybridRouter is the canonical implementation for Phase14+.
This file is kept for backward compatibility — loop_controller.py
imports `from agent_router import route as router_route`.
"""

import os
import sys
from datetime import datetime, timezone

BASE = "/home/shade/.agents"

# Import the canonical HybridRouter (Phase14)
sys.path.insert(0, os.path.join(BASE, "runtime", "router"))
from hybrid_router import HybridRouter, get_hybrid_router

# Lazy singleton — initialized on first call
_router = None


def _ensure_router():
    global _router
    if _router is None:
        _router = get_hybrid_router()
    return _router


def classify_intent(task_text: str) -> dict:
    """
    Classify task intent and domains.
    Delegates to HybridRouter.
    """
    router = _ensure_router()
    c = router.route(task_text)
    return {
        "intent": c.intent,
        "domains": c.domains,
    }


def route(task_text: str, memory_context: dict = None) -> dict:
    """
    Route a task to the appropriate skill(s).

    This is the backward-compatible wrapper. Phase14 Repair: delegates to
    the HybridRouter (runtime/router/hybrid_router.py) instead of the
    Phase13.1 Router.

    Args:
        task_text: The task description
        memory_context: Optional dict with memories that may influence routing

    Returns:
        dict: RouteDecision (backward-compatible shape, with Phase14 additions)
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
        "confidence_numeric": decision.confidence_numeric,
        "fallback_reason": decision.fallback_reason,
        "candidates": decision.candidates,
        "scores": decision.scores,
        "difficulty": decision.difficulty,
        "memory_influence": decision.memory_influence,
        "memory_retrieved": decision.memory_retrieved,
        "rules_applied": decision.rules_applied,
        "router_version": decision.router_version,
        "started_at": decision.started_at,
        "completed_at": decision.completed_at,
        "artifact": decision.to_artifact(),
        # Phase14 additions
        "route_mode": getattr(decision, "route_mode", "lexical"),
        "escalation_reason": getattr(decision, "escalation_reason", None),
        "semantic_features": getattr(decision, "semantic_features", None),
    }