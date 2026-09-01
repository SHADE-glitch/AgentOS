#!/usr/bin/env python3
"""
Retrieval Adapter — Phase 7.1

Bridges between task input and retrieval_optimizer.

Task → Router.classify() → retrieval_optimizer.retrieve() → DecisionContext

Classification is delegated to the canonical Router Runtime
(runtime/router/router.py). This adapter is responsible for
retrieval only — not routing logic.

This is NOT an Agent. It does NOT decide team formation.
It only classifies the task and queries existing Memory.
"""

import sys
import os
import re
from datetime import datetime, timezone

# Allow importing retrieval_optimizer from sibling package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "memory-feedback", "retrieval"))
from retrieval_optimizer import retrieve as retrieval_retrieve, save_retrieval_history

BASE = "/home/shade/.agents"

# Import the canonical Router Runtime for classification
sys.path.insert(0, os.path.join(BASE, "runtime", "router"))
from router import get_router

# Lazy singleton
_router = None


def _ensure_router():
    global _router
    if _router is None:
        _router = get_router()
    return _router


# ---------------------------------------------------------------------------
# Task Classification (delegated to Router Runtime)
# ---------------------------------------------------------------------------

def classify_task(task_text):
    """
    Classify a task into category, domains, roles, keywords, difficulty.

    Delegates to the canonical Router Runtime (runtime/router/router.py).
    Uses simple keyword matching — no ML, no external deps.

    Returns dict — backward compatible with existing callers.
    """
    router = _ensure_router()
    result = router.classify(task_text)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

def adapt(task_id, task_text, memory_mode):
    """
    Bridge: task → retrieval_optimizer.retrieve() → DecisionContext

    Args:
        task_id: str like "RT-003"
        task_text: str, the task description
        memory_mode: "enabled" | "fallback" | "disabled"

    Returns:
        DecisionContext dict with retrieval results, or empty context if disabled.
    """
    if memory_mode in ("disabled", "off"):
        return {
            "task_id": task_id,
            "task_text": task_text,
            "memory_mode": memory_mode,
            "retrieved": False,
            "memories": [],
            "hypotheses": [],
            "total_retrieved": 0,
            "ranking": [],
            "retrieval_raw": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Classify task
    query = classify_task(task_text)
    query["exclude_hypothesis"] = False

    # Phase 5.8.2.2: Always retrieve — but label hypotheses separately
    raw_result = retrieval_retrieve(query)

    # Separate hypotheses from established memories
    memories = []
    hypotheses = []
    for r in raw_result.get("results", []):
        if r.get("is_hypothesis") or r.get("type") == "hypothesis":
            hypotheses.append(r)
        else:
            memories.append(r)

    # Save retrieval history for decay tracking
    try:
        save_retrieval_history(query, raw_result)
    except Exception:
        pass  # Non-critical

    return {
        "task_id": task_id,
        "task_text": task_text,
        "memory_mode": memory_mode,
        "retrieved": True,
        "memories": memories,
        "hypotheses": hypotheses,
        "total_retrieved": raw_result.get("top_k", 0),
        "total_considered": raw_result.get("total_considered", 0),
        "after_filter": raw_result.get("after_filter", 0),
        "ranking": [m["memory_id"] for m in memories],
        "retrieval_raw": raw_result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml

    if len(sys.argv) < 3:
        print("Usage: python3 retrieval_adapter.py <task_id> <task_text> [memory_mode]")
        print("Example: python3 retrieval_adapter.py RT-003 '分析 MySQL 慢查询问题' enabled")
        sys.exit(1)

    task_id = sys.argv[1]
    task_text = sys.argv[2]
    memory_mode = sys.argv[3] if len(sys.argv) > 3 else "enabled"

    result = adapt(task_id, task_text, memory_mode)
    print(yaml.dump(result, default_flow_style=False, allow_unicode=True, sort_keys=False))