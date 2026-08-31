#!/usr/bin/env python3
"""
Adaptive Memory Retrieval Optimizer — Phase 5.8
Implements adaptive scoring that extends the static retrieval protocol
with runtime performance feedback.

Scoring formula:
  memory_score = relevance_score * 0.35
               + success_rate    * 0.25
               + confidence_score * 0.20
               + performance_gain * 0.20

Input:  task description (query)
        retrieval-index.yaml (memory metadata + usage data)
        effectiveness-results.yaml (performance data)

Output: Top-K memories ranked by adaptive_score
"""

import yaml
import os
import re
from datetime import datetime, timezone
from collections import OrderedDict

# Paths
RETRIEVAL_INDEX = "/home/shade/.agents/memory/retrieval-index.yaml"
EFFECTIVENESS_RESULTS = "/home/shade/.agents/runtime/memory-feedback/evaluation/effectiveness-results.yaml"
TRACES_DIR = "/home/shade/.agents/runtime/traces"
RETRIEVAL_HISTORY = "/home/shade/.agents/runtime/memory-feedback/retrieval/retrieval-history.yaml"
SCORING_LOG = "/home/shade/.agents/runtime/memory-feedback/retrieval/scoring-log.yaml"

# Scoring weights
WEIGHTS = {
    "relevance": 0.35,
    "success_rate": 0.25,
    "confidence": 0.20,
    "performance": 0.20,
}

# Thresholds
TOP_K = 5
MIN_SCORE = 0.15


def clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def load_yaml(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath) as f:
        return yaml.safe_load(f)


def load_retrieval_index():
    return load_yaml(RETRIEVAL_INDEX)


def load_effectiveness_data():
    return load_yaml(EFFECTIVENESS_RESULTS)


def load_usage_from_traces():
    """Build per-memory usage statistics from trace files."""
    usage = {}
    for fname in sorted(os.listdir(TRACES_DIR)):
        if not fname.endswith(".yaml"):
            continue
        trace = load_yaml(os.path.join(TRACES_DIR, fname))
        if not trace:
            continue
        eid = trace.get("execution_id", "")
        status = trace.get("status", "unknown")
        is_success = status == "success"
        mem_used = trace.get("memory_retrieval", {}).get("memories_used", [])

        for mid in mem_used:
            if mid not in usage:
                usage[mid] = {
                    "usage_count": 0,
                    "successful_uses": 0,
                    "executions": [],
                }
            usage[mid]["usage_count"] += 1
            if is_success:
                usage[mid]["successful_uses"] += 1
            usage[mid]["executions"].append(eid)

    return usage


def load_evaluation_by_memory():
    """Extract per-memory performance deltas from effectiveness results."""
    eval_data = load_effectiveness_data()
    perf = {}

    raw = eval_data.get("raw_data", {}).get("trace_metrics", [])
    if not raw:
        return perf

    # Build per-memory quality data from trace metrics
    mem_quality = {}
    mem_without_quality = {}
    for m in raw:
        quality = m.get("quality_score", 0)
        mids = m.get("memories_used", [])
        for mid in mids:
            if mid not in mem_quality:
                mem_quality[mid] = []
            mem_quality[mid].append(quality)

    # For each memory, compute quality delta vs all traces
    all_qualities = [m.get("quality_score", 0) for m in raw]
    avg_all = sum(all_qualities) / len(all_qualities) if all_qualities else 0

    for mid, qualities in mem_quality.items():
        avg_with = sum(qualities) / len(qualities)
        # quality_delta: positive = better than average
        quality_delta = avg_with - avg_all

        # Token and latency deltas from trace raw data
        tokens_with = []
        tokens_without = []
        latencies_with = []
        latencies_without = []

        for m in raw:
            mids = m.get("memories_used", [])
            if mid in mids:
                tokens_with.append(m.get("tokens_total", 0))
                latencies_with.append(m.get("latency_ms", 0))
            else:
                tokens_without.append(m.get("tokens_total", 0))
                latencies_without.append(m.get("latency_ms", 0))

        avg_tokens_with = sum(tokens_with) / len(tokens_with) if tokens_with else 0
        avg_tokens_without = sum(tokens_without) / len(tokens_without) if tokens_without else 0
        avg_latency_with = sum(latencies_with) / len(latencies_with) if latencies_with else 0
        avg_latency_without = sum(latencies_without) / len(latencies_without) if latencies_without else 0

        token_delta_pct = ((avg_tokens_with - avg_tokens_without) / avg_tokens_without * 100) if avg_tokens_without > 0 else 0
        latency_delta_ms = avg_latency_with - avg_latency_without

        # Compute performance gain
        quality_norm = clamp((quality_delta / 2.5) + 0.5, 0, 1)
        token_norm = clamp(1.0 - (avg_tokens_with / avg_tokens_without), 0, 1) if avg_tokens_without > 0 else 0
        latency_norm = clamp(1.0 - (avg_latency_with / avg_latency_without), 0, 1) if avg_latency_without > 0 else 0

        performance_gain = quality_norm * 0.4 + token_norm * 0.3 + latency_norm * 0.3

        perf[mid] = {
            "quality_delta": round(quality_delta, 2),
            "token_delta_pct": round(token_delta_pct, 1),
            "latency_delta_ms": round(latency_delta_ms, 2),
            "performance_gain": round(performance_gain, 3),
        }

    return perf


def compute_static_relevance(memory, query):
    """
    Compute static relevance score from retrieval-protocol.md Section 4.
    This is a deterministic, metadata-driven score.
    """
    category = memory.get("category", "")
    tags = [t.lower() for t in memory.get("tags", [])]

    q_category = query.get("category", "").lower()
    q_domains = [d.lower() for d in query.get("domains", [])]
    q_roles = [r.lower() for r in query.get("roles", [])]
    q_keywords = [k.lower() for k in query.get("keywords", [])]

    # Category match
    category_match = 1.0 if q_category and q_category in category.lower() else 0.0

    # Domain match
    domain_match = 0.0
    if q_domains:
        domain_overlap = sum(1 for d in q_domains if d in tags)
        domain_match = domain_overlap / max(len(q_domains), 1)

    # Role match
    role_match = 0.0
    if q_roles:
        role_overlap = sum(1 for r in q_roles if r in tags)
        role_match = role_overlap / max(len(q_roles), 1)

    # Keyword match
    keyword_match = 0.0
    if q_keywords:
        kw_overlap = sum(1 for k in q_keywords if k in tags)
        keyword_match = kw_overlap / max(len(q_keywords), 1)

    # Type boost
    mem_type = memory.get("type", "")
    type_boost = 0.0
    if mem_type == "failure" and any(d in tags for d in q_domains):
        type_boost = 0.15
    elif mem_type == "anti-pattern" and len(q_domains) <= 1:
        type_boost = 0.15
    elif mem_type == "pattern" and len(q_domains) >= 2:
        type_boost = 0.05

    # Difficulty match
    difficulty_match = 0.0
    q_diff = query.get("difficulty", "").lower()
    if q_diff and q_diff in memory.get("difficulty", "").lower():
        difficulty_match = 0.10

    # Tag overlap
    tag_overlap = 0.0
    if tags:
        all_query_tags = set(q_domains + q_roles + q_keywords)
        tag_overlap = len(set(tags) & all_query_tags) / max(len(tags), 1)
        tag_overlap = min(tag_overlap, 0.05)

    # Weights from retrieval-protocol.md
    relevance = (
        category_match * 0.25 +
        domain_match * 0.20 +
        type_boost * 0.15 +
        role_match * 0.15 +
        keyword_match * 0.10 +
        difficulty_match * 0.10 +
        tag_overlap * 0.05
    )

    return round(relevance, 3)


def compute_adaptive_score(memory, static_relevance, usage_data, eval_data, decay_factor=1.0):
    """
    Compute the adaptive score for a memory.
    """
    memory_id = memory["memory_id"]

    # 1. Static relevance
    relevance_score = static_relevance

    # 2. Success rate
    usage = usage_data.get(memory_id, {})
    uc = usage.get("usage_count", 0)
    su = usage.get("successful_uses", 0)
    success_rate = (su / uc) if uc > 0 else 0.5

    # 3. Confidence score
    obs_count = memory.get("observation_count", 0)
    confidence_score = min(obs_count / 5.0, 1.0)

    # 4. Performance gain
    perf = eval_data.get(memory_id, {})
    performance_gain = perf.get("performance_gain", 0.0)

    # Adaptive score
    adaptive = (
        relevance_score * WEIGHTS["relevance"] +
        success_rate * WEIGHTS["success_rate"] +
        confidence_score * WEIGHTS["confidence"] +
        performance_gain * WEIGHTS["performance"]
    )

    # Apply decay
    final_score = adaptive * decay_factor

    return {
        "memory_id": memory_id,
        "static_relevance": round(relevance_score, 3),
        "success_rate": round(success_rate, 3),
        "confidence_score": round(confidence_score, 3),
        "performance_gain": round(performance_gain, 3),
        "adaptive_score": round(adaptive, 3),
        "decay_factor": round(decay_factor, 3),
        "final_score": round(final_score, 3),
        "evidence_level": memory.get("evidence_level", "hypothesis"),
        "confidence": memory.get("confidence", "low"),
        "type": memory.get("type", "unknown"),
        "category": memory.get("category", ""),
        "tags": memory.get("tags", []),
        "usage_count": uc,
        "is_hypothesis": memory.get("type") == "hypothesis",
        "warning": "Unvalidated hypothesis — not an established engineering rule" if memory.get("type") == "hypothesis" else None,
    }


def _ensure_reconciled():
    """Phase 5.8.1: Verify index is consistent with canonical state before retrieval."""
    import subprocess
    reconciler = os.path.join(os.path.dirname(__file__), "memory_state_reconciler.py")
    if not os.path.exists(reconciler):
        return
    result = subprocess.run(
        ["python3", reconciler, "--check"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: State inconsistency detected. Run repair first.")
        print(result.stdout.strip()[:200])


def retrieve(query, decay_factors=None):
    """
    Main retrieval function.
    
    Args:
        query: dict with task_text, category, domains, roles, keywords, difficulty
        decay_factors: optional dict of memory_id -> decay_factor
    
    Returns:
        dict with ranked memories and metadata
    """
    # Phase 5.8.1: Ensure index is reconciled before retrieval
    _ensure_reconciled()
    
    index = load_retrieval_index()
    memories = index.get("memories", [])

    if not memories:
        return {"query": query, "results": [], "error": "No memories in index"}

    usage_data = load_usage_from_traces()
    eval_data = load_evaluation_by_memory()

    if decay_factors is None:
        decay_factors = {}

    results = []
    for mem in memories:
        mid = mem["memory_id"]

        # Skip hypothesis if query explicitly excludes them
        if mem.get("type") == "hypothesis" and query.get("exclude_hypothesis", False):
            continue

        if mid in query.get("exclude_memories", []):
            continue

        static_rel = compute_static_relevance(mem, query)
        decay = decay_factors.get(mid, 1.0)
        result = compute_adaptive_score(mem, static_rel, usage_data, eval_data, decay)

        # Filter by min score
        if result["final_score"] < MIN_SCORE:
            continue

        results.append(result)

    # Sort by final_score descending
    results.sort(key=lambda r: r["final_score"], reverse=True)

    # Top-K
    top_k = results[:TOP_K]

    # Compute match reasons for each result
    for r in top_k:
        reasons = []
        if r["static_relevance"] > 0.3:
            reasons.append(f"relevance={r['static_relevance']}")
        if r["success_rate"] > 0.5:
            reasons.append(f"success_rate={r['success_rate']}")
        if r["confidence_score"] > 0:
            reasons.append(f"confidence={r['confidence_score']}")
        if r["performance_gain"] > 0.5:
            reasons.append(f"perf_gain={r['performance_gain']}")
        if r["decay_factor"] < 1.0:
            reasons.append(f"decayed={r['decay_factor']}")
        if not reasons:
            reasons.append("default_match")
        r["match_reasons"] = reasons

    return {
        "query": query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_considered": len(memories),
        "after_filter": len(results),
        "top_k": len(top_k),
        "results": top_k,
    }


def format_retrieval_output(retrieval_result):
    """Format retrieval results for human-readable output."""
    lines = []
    lines.append(f"Query: {retrieval_result['query'].get('task_text', '?')[:80]}")
    lines.append(f"Category: {retrieval_result['query'].get('category', '?')}")
    lines.append(f"Domains: {retrieval_result['query'].get('domains', [])}")
    lines.append(f"Considered: {retrieval_result['total_considered']} → Filtered: {retrieval_result['after_filter']} → Top-{retrieval_result['top_k']}")
    lines.append("")

    for i, r in enumerate(retrieval_result["results"]):
        lines.append(f"  #{i+1} {r['memory_id']} ({r['type']})")
        lines.append(f"      final_score: {r['final_score']}  adaptive: {r['adaptive_score']}  static: {r['static_relevance']}")
        lines.append(f"      success: {r['success_rate']}  confidence: {r['confidence_score']}  perf: {r['performance_gain']}  decay: {r['decay_factor']}")
        lines.append(f"      evidence: {r['evidence_level']}  confidence: {r['confidence']}  uses: {r['usage_count']}")
        if r.get("warning"):
            lines.append(f"      ⚠ {r['warning']}")
        lines.append(f"      reasons: {r['match_reasons']}")
        lines.append("")

    return "\n".join(lines)


def save_retrieval_history(query, result):
    """Save retrieval history for decay tracking."""
    history = load_yaml(RETRIEVAL_HISTORY)
    if not history:
        history = {"version": "1.0", "phase": "5.8", "retrievals": []}

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "retrieved_memories": [r["memory_id"] for r in result.get("results", [])],
    }
    history["retrievals"].append(entry)

    os.makedirs(os.path.dirname(RETRIEVAL_HISTORY), exist_ok=True)
    with open(RETRIEVAL_HISTORY, "w") as f:
        yaml.dump(history, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# =============================================================================
# Test: 10 simulated tasks
# =============================================================================

TEST_TASKS = [
    {
        "task_text": "Design a payment system with PCI-DSS compliance",
        "category": "backend",
        "domains": ["payment", "security"],
        "roles": ["backend-architect", "security-engineer"],
        "keywords": ["pci-dss", "compliance", "payment", "kms"],
        "difficulty": "medium",
    },
    {
        "task_text": "Analyze MySQL slow query performance",
        "category": "optimization",
        "domains": ["database"],
        "roles": ["database-engineer"],
        "keywords": ["mysql", "slow-query", "indexing", "optimization"],
        "difficulty": "easy",
    },
    {
        "task_text": "Build a RAG system with vector retrieval",
        "category": "ai",
        "domains": ["rag", "vector-store"],
        "roles": ["rag-engineer", "llm-engineer"],
        "keywords": ["rag", "vector", "retrieval", "embedding", "reranking"],
        "difficulty": "medium",
    },
    {
        "task_text": "Design a distributed seckill system",
        "category": "architecture",
        "domains": ["architecture", "distributed"],
        "roles": ["system-architect", "backend-architect", "distributed-system"],
        "keywords": ["seckill", "high-concurrency", "lua", "distributed"],
        "difficulty": "hard",
    },
    {
        "task_text": "Implement tool-calling for an LLM agent",
        "category": "ai",
        "domains": ["agent", "tool-calling"],
        "roles": ["llm-engineer", "agent-engineer", "prompt-engineer"],
        "keywords": ["tool-calling", "agent", "llm", "prompt"],
        "difficulty": "medium",
    },
    {
        "task_text": "Build a multi-tenant AI SaaS platform",
        "category": "architecture",
        "domains": ["architecture", "ai", "multi-tenant"],
        "roles": ["system-architect", "rag-engineer", "backend-architect"],
        "keywords": ["ai-saas", "multi-tenant", "rag", "isolation"],
        "difficulty": "hard",
    },
    {
        "task_text": "Optimize high-concurrency distributed system",
        "category": "optimization",
        "domains": ["distributed", "concurrency"],
        "roles": ["distributed-system", "backend-architect"],
        "keywords": ["high-concurrency", "distributed", "optimization", "rollback"],
        "difficulty": "hard",
    },
    {
        "task_text": "Build an admin platform with RBAC",
        "category": "frontend",
        "domains": ["frontend", "backend"],
        "roles": ["frontend-architect", "backend-architect", "code-reviewer"],
        "keywords": ["admin", "rbac", "api-contract", "frontend-backend"],
        "difficulty": "medium",
    },
    {
        "task_text": "Design a cross-domain distributed architecture",
        "category": "architecture",
        "domains": ["architecture", "backend", "distributed"],
        "roles": ["system-architect", "backend-architect", "distributed-system", "database-engineer"],
        "keywords": ["cross-domain", "architecture", "backend", "saga", "seckill"],
        "difficulty": "hard",
    },
    {
        "task_text": "Optimize SPA frontend performance",
        "category": "frontend",
        "domains": ["frontend"],
        "roles": ["frontend-performance", "frontend-architect"],
        "keywords": ["spa", "performance", "frontend", "optimization"],
        "difficulty": "easy",
    },
]


def main():
    print("=" * 70)
    print("Phase 5.8 — Adaptive Memory Retrieval Optimizer")
    print("=" * 70)

    # Load data
    index = load_retrieval_index()
    memories = index.get("memories", [])
    print(f"Loaded {len(memories)} memories from retrieval-index.yaml")

    usage_data = load_usage_from_traces()
    print(f"Usage data: {len(usage_data)} memories with execution history")

    eval_data = load_evaluation_by_memory()
    print(f"Performance data: {len(eval_data)} memories with evaluation data")

    # Print per-memory performance summary
    print("\n--- Performance Data by Memory ---")
    for mid, data in sorted(eval_data.items()):
        print(f"  {mid}: quality_delta={data['quality_delta']}, "
              f"token_delta={data['token_delta_pct']}%, "
              f"latency_delta={data['latency_delta_ms']}ms, "
              f"perf_gain={data['performance_gain']}")

    # Run 10 test tasks
    all_results = []
    print("\n" + "=" * 70)
    print("Running 10 Test Tasks")
    print("=" * 70)

    for i, task in enumerate(TEST_TASKS):
        print(f"\n--- Task {i+1}: {task['task_text'][:70]} ---")
        result = retrieve(task)
        all_results.append(result)
        print(format_retrieval_output(result))

        # Save history
        save_retrieval_history(task, result)

    # Summary
    print("\n" + "=" * 70)
    print("Retrieval Summary")
    print("=" * 70)

    memory_appearances = {}
    for result in all_results:
        for r in result["results"]:
            mid = r["memory_id"]
            if mid not in memory_appearances:
                memory_appearances[mid] = {"count": 0, "avg_score": 0, "scores": []}
            memory_appearances[mid]["count"] += 1
            memory_appearances[mid]["scores"].append(r["final_score"])

    for mid, data in sorted(memory_appearances.items(), key=lambda x: -x[1]["count"]):
        data["avg_score"] = round(sum(data["scores"]) / len(data["scores"]), 3)
        print(f"  {mid}: appeared {data['count']}x, avg_score={data['avg_score']}")

    # Save scoring log
    log = {
        "version": "1.0",
        "phase": "5.8",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_tasks": len(TEST_TASKS),
        "results": [],
        "memory_appearances": {mid: data for mid, data in sorted(memory_appearances.items(), key=lambda x: -x[1]["count"])},
    }
    for i, result in enumerate(all_results):
        log["results"].append({
            "task_index": i + 1,
            "query": result["query"],
            "top_5": [r["memory_id"] for r in result["results"]],
            "top_5_scores": [r["final_score"] for r in result["results"]],
        })

    os.makedirs(os.path.dirname(SCORING_LOG), exist_ok=True)
    with open(SCORING_LOG, "w") as f:
        yaml.dump(log, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\nScoring log saved to: {SCORING_LOG}")
    print(f"Retrieval history saved to: {RETRIEVAL_HISTORY}")


if __name__ == "__main__":
    main()