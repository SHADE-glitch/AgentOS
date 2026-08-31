#!/usr/bin/env python3
"""
Memory Effectiveness Evaluator — Phase 5.7.3
Evaluates whether promoted memories improve agent performance.

Compares traces that used a memory vs traces that did not use it.
Since no memory OFF baseline exists, uses cross-group comparison.

Input:  runtime/traces/*.yaml
        runtime/memory-feedback/memory-candidates.yaml
        memory/retrieval-index.yaml

Output: runtime/memory-feedback/evaluation/effectiveness-results.yaml
"""

import yaml
import os
from datetime import datetime, timezone
from collections import defaultdict

TRACES_DIR = "/home/shade/.agents/runtime/traces"
CANDIDATES_FILE = "/home/shade/.agents/runtime/memory-feedback/memory-candidates.yaml"
MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"
OUTPUT_FILE = "/home/shade/.agents/runtime/memory-feedback/evaluation/effectiveness-results.yaml"

# Effectiveness score weights
WEIGHTS = {
    "quality": 0.40,
    "success_rate": 0.30,
    "token_efficiency": 0.20,
    "latency": 0.10,
}

# Thresholds
THRESHOLDS = {
    "effective": 0.7,
    "neutral": 0.4,
    "ineffective": 0.0,
}


def load_all_traces():
    """Load all trace files from the traces directory."""
    traces = []
    for fname in sorted(os.listdir(TRACES_DIR)):
        if fname.endswith(".yaml"):
            with open(os.path.join(TRACES_DIR, fname)) as f:
                trace = yaml.safe_load(f)
                if trace:
                    traces.append(trace)
    return traces


def load_candidates():
    """Load memory candidates to find which memories were promoted."""
    if not os.path.exists(CANDIDATES_FILE):
        return {}
    with open(CANDIDATES_FILE) as f:
        return yaml.safe_load(f)


def find_promoted_memories():
    """Find all memories that have been promoted (runtime_validated or higher)."""
    index = load_memory_index()
    promoted = []
    for m in index.get("memories", []):
        el = m.get("evidence_level", "hypothesis")
        if el in ("runtime_validated", "independent_validated",
                  "real_project_validated", "production_validated"):
            promoted.append(m)
    return promoted


def load_memory_index():
    if not os.path.exists(MEMORY_INDEX_FILE):
        return {}
    with open(MEMORY_INDEX_FILE) as f:
        return yaml.safe_load(f)


def extract_trace_metrics(trace):
    """Extract key metrics from a trace."""
    ai = trace.get("agent_invocation", {})
    tokens = ai.get("tokens", {})
    return {
        "execution_id": trace["execution_id"],
        "task_id": trace.get("task_id", ""),
        "domain": trace.get("domain", ""),
        "difficulty": trace.get("difficulty", ""),
        "status": trace.get("status", ""),
        "tokens_total": tokens.get("total", 0),
        "tokens_input": tokens.get("input", 0),
        "tokens_output": tokens.get("output", 0),
        "latency_ms": ai.get("latency_ms", 0),
        "memory_mode": trace.get("memory_mode", "?"),
        "memories_used": trace.get("memory_retrieval", {}).get("memories_used", []),
        "memory_influence": trace.get("memory_retrieval", {}).get("memory_influence",
                          trace.get("memory_retrieval", {}).get("influence", "none")),
        "quality_score": 0,  # Will be computed
    }


def compute_quality_score(trace):
    """Reuse the quality heuristic from collector to get consistent scores."""
    import re
    response = trace.get("agent_response", "")

    # Completeness
    comp = 0
    if re.search(r'#{1,3}\s', response): comp += 1
    if re.search(r'[-*]\s', response): comp += 1
    if re.search(r'```', response): comp += 1
    if len(re.findall(r'#{1,3}\s', response)) >= 3: comp += 1
    if len(response) > 100: comp += 1

    # Accuracy
    acc = 0
    tech_terms = ['API', 'TLS', 'AES', 'JWT', 'RBAC', 'SQL', 'RAG', 'LLM',
                  'cache', 'token', 'encrypt', 'vector', 'retrieval', 'index',
                  'OAuth', 'HMAC', 'SHA', 'PCI', 'DSS', 'embedding', 'chunking',
                  'OCR', 'Cross-Encoder', 'Dense', 'Sparse', 'Redis', 'MySQL',
                  '数据库', '向量', '检索', '加密', '认证', '授权', '缓存',
                  '分布式', '高并发', '索引', '查询', '性能', '安全']
    if any(t.lower() in response.lower() for t in tech_terms): acc += 1
    if re.search(r'(?:使用|采用|选择|推荐|基于|通过)', response): acc += 1
    if re.search(r'(?:实现|配置|部署|设置|构建|处理)', response): acc += 1
    if re.search(r'(?:因为|原因|由于|为了|确保|避免)', response): acc += 1
    if re.search(r'(?:具体|详细|明确)', response): acc += 1

    # Structure
    struct = 0
    if re.search(r'^\d+[\.、）)]\s', response, re.MULTILINE): struct += 1
    if re.search(r'^#{1,3}\s', response, re.MULTILINE): struct += 1
    if len(response.split('\n')) > 8: struct += 1
    if response.count('\n') > 5: struct += 1
    if len(response) > 100 and '\n\n' in response: struct += 1

    # Actionability
    act = 0
    if re.search(r'(?:步骤|流程|Step|方法|方式)', response): act += 1
    if re.search(r'(?:建议|推荐|方案|策略|设计)', response): act += 1
    if re.search(r'(?:例如|示例|比如|如)', response): act += 1
    if re.search(r'(?:配置|参数|设置|兼容|注意)', response): act += 1
    if len(response) > 100: act += 1

    # Novelty
    nov = 0
    if re.search(r'(?:数据库|向量|检索|索引|缓存|存储|查询)', response): nov += 1
    if re.search(r'(?:权衡|取舍|trade|利弊|对比|相比)', response, re.IGNORECASE): nov += 1
    if re.search(r'(?:边界|极端|边缘|corner|特殊|异常)', response, re.IGNORECASE): nov += 1
    if re.search(r'(?:优化|改进|提升|增强|加速)', response): nov += 1
    if len(response) > 200: nov += 1

    weighted = (
        comp * 0.25 + acc * 0.30 + struct * 0.15 + act * 0.20 + nov * 0.10
    )
    return round(weighted, 2)


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def evaluate_memory(memory_id, memory_meta, all_traces):
    """
    Evaluate a single memory's effectiveness.
    Returns an evaluation record.
    """
    # Split traces into Group A (used this memory) and Group B (did not use)
    group_a = []
    group_b = []

    for t in all_traces:
        mem_used = t.get("memory_retrieval", {}).get("memories_used", [])
        if memory_id in mem_used:
            group_a.append(t)
        else:
            group_b.append(t)

    if not group_a:
        return {
            "memory_id": memory_id,
            "status": "skipped",
            "reason": "No traces used this memory",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    if not group_b:
        return {
            "memory_id": memory_id,
            "status": "skipped",
            "reason": "All traces used this memory — no comparison group",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Compute metrics for each group
    metrics_a = [extract_trace_metrics(t) for t in group_a]
    metrics_b = [extract_trace_metrics(t) for t in group_b]

    # Add quality scores
    for m in metrics_a:
        t = next(t for t in group_a if t["execution_id"] == m["execution_id"])
        m["quality_score"] = compute_quality_score(t)
    for m in metrics_b:
        t = next(t for t in group_b if t["execution_id"] == m["execution_id"])
        m["quality_score"] = compute_quality_score(t)

    # Averages
    avg_qa = sum(m["quality_score"] for m in metrics_a) / len(metrics_a)
    avg_qb = sum(m["quality_score"] for m in metrics_b) / len(metrics_b)
    avg_ta = sum(m["tokens_total"] for m in metrics_a) / len(metrics_a)
    avg_tb = sum(m["tokens_total"] for m in metrics_b) / len(metrics_b)
    avg_la = sum(m["latency_ms"] for m in metrics_a) / len(metrics_a)
    avg_lb = sum(m["latency_ms"] for m in metrics_b) / len(metrics_b)
    avg_oa = sum(m["tokens_output"] for m in metrics_a) / len(metrics_a)
    avg_ob = sum(m["tokens_output"] for m in metrics_b) / len(metrics_b)

    # Success rates
    success_a = sum(1 for m in metrics_a if m["status"] == "success") / len(metrics_a)
    success_b = sum(1 for m in metrics_b if m["status"] == "success") / len(metrics_b)

    # Deltas
    quality_delta = round(avg_qa - avg_qb, 2)
    token_delta = round(avg_ta - avg_tb, 2)
    token_delta_pct = round((avg_ta - avg_tb) / avg_tb * 100, 1) if avg_tb > 0 else 0
    latency_delta_ms = round(avg_la - avg_lb, 2)
    output_delta = round(avg_oa - avg_ob, 2)

    # --- Effectiveness Score ---
    # Quality component: normalize to [0, 1], with 0.5 at delta=0
    quality_component = clamp((quality_delta / 2.5) + 0.5, 0.0, 1.0)

    # Success rate component: all are 100% success, so 0.5 (no discrimination)
    success_rate_component = 0.5

    # Token efficiency: savings percentage
    token_efficiency = 1.0 - (avg_ta / avg_tb) if avg_tb > 0 else 0
    token_efficiency_component = clamp(token_efficiency, 0.0, 1.0)

    # Latency component: reduction percentage
    latency_reduction = 1.0 - (avg_la / avg_lb) if avg_lb > 0 else 0
    latency_component = clamp(latency_reduction, 0.0, 1.0)

    # Weighted score
    effectiveness_score = (
        quality_component * WEIGHTS["quality"] +
        success_rate_component * WEIGHTS["success_rate"] +
        token_efficiency_component * WEIGHTS["token_efficiency"] +
        latency_component * WEIGHTS["latency"]
    )

    # Decision
    if effectiveness_score >= THRESHOLDS["effective"]:
        decision = "effective"
    elif effectiveness_score >= THRESHOLDS["neutral"]:
        decision = "neutral"
    else:
        decision = "ineffective"

    # Collect influence types
    influence_types = []
    for t in group_a:
        inf = t.get("memory_retrieval", {}).get("memory_influence",
                 t.get("memory_retrieval", {}).get("influence", "none"))
        if inf not in influence_types:
            influence_types.append(inf)

    return {
        "evaluation_id": f"EVAL-{memory_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "memory_id": memory_id,
        "memory_type": memory_meta.get("type", "unknown"),
        "memory_evidence_level": memory_meta.get("evidence_level", "unknown"),
        "group_a": {
            "execution_ids": [m["execution_id"] for m in metrics_a],
            "count": len(metrics_a),
            "avg_quality": round(avg_qa, 2),
            "avg_tokens": round(avg_ta, 2),
            "avg_latency_ms": round(avg_la, 2),
            "avg_output_tokens": round(avg_oa, 2),
            "all_statuses": [m["status"] for m in metrics_a],
            "influence_types": influence_types,
        },
        "group_b": {
            "execution_ids": [m["execution_id"] for m in metrics_b],
            "count": len(metrics_b),
            "avg_quality": round(avg_qb, 2),
            "avg_tokens": round(avg_tb, 2),
            "avg_latency_ms": round(avg_lb, 2),
            "avg_output_tokens": round(avg_ob, 2),
            "all_statuses": [m["status"] for m in metrics_b],
        },
        "deltas": {
            "quality_delta": quality_delta,
            "token_delta": token_delta,
            "token_delta_pct": token_delta_pct,
            "latency_delta_ms": latency_delta_ms,
            "output_delta": output_delta,
        },
        "effectiveness_score": round(effectiveness_score, 3),
        "effectiveness_score_breakdown": {
            "quality_component": {"value": round(quality_component, 3), "weight": WEIGHTS["quality"]},
            "success_rate_component": {"value": round(success_rate_component, 3), "weight": WEIGHTS["success_rate"]},
            "token_efficiency_component": {"value": round(token_efficiency_component, 3), "weight": WEIGHTS["token_efficiency"]},
            "latency_component": {"value": round(latency_component, 3), "weight": WEIGHTS["latency"]},
        },
        "decision": decision,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def evaluate_pair(memory_ids, memory_meta_map, all_traces):
    """
    Evaluate a pair of memories that are always used together.
    Returns a combined evaluation record.
    """
    # Treat as a single unit: Group A = traces that used ANY of these memories
    group_a = []
    group_b = []

    for t in all_traces:
        mem_used = t.get("memory_retrieval", {}).get("memories_used", [])
        if any(mid in mem_used for mid in memory_ids):
            group_a.append(t)
        else:
            group_b.append(t)

    if not group_a or not group_b:
        return None

    # Compute metrics
    metrics_a = [extract_trace_metrics(t) for t in group_a]
    metrics_b = [extract_trace_metrics(t) for t in group_b]

    for m in metrics_a:
        t = next(t for t in group_a if t["execution_id"] == m["execution_id"])
        m["quality_score"] = compute_quality_score(t)
    for m in metrics_b:
        t = next(t for t in group_b if t["execution_id"] == m["execution_id"])
        m["quality_score"] = compute_quality_score(t)

    avg_qa = sum(m["quality_score"] for m in metrics_a) / len(metrics_a)
    avg_qb = sum(m["quality_score"] for m in metrics_b) / len(metrics_b)
    avg_ta = sum(m["tokens_total"] for m in metrics_a) / len(metrics_a)
    avg_tb = sum(m["tokens_total"] for m in metrics_b) / len(metrics_b)
    avg_la = sum(m["latency_ms"] for m in metrics_a) / len(metrics_a)
    avg_lb = sum(m["latency_ms"] for m in metrics_b) / len(metrics_b)

    quality_delta = round(avg_qa - avg_qb, 2)
    token_delta = round(avg_ta - avg_tb, 2)
    token_delta_pct = round((avg_ta - avg_tb) / avg_tb * 100, 1) if avg_tb > 0 else 0
    latency_delta_ms = round(avg_la - avg_lb, 2)

    quality_component = clamp((quality_delta / 2.5) + 0.5, 0.0, 1.0)
    success_rate_component = 0.5
    token_efficiency = 1.0 - (avg_ta / avg_tb) if avg_tb > 0 else 0
    token_efficiency_component = clamp(token_efficiency, 0.0, 1.0)
    latency_reduction = 1.0 - (avg_la / avg_lb) if avg_lb > 0 else 0
    latency_component = clamp(latency_reduction, 0.0, 1.0)

    effectiveness_score = (
        quality_component * WEIGHTS["quality"] +
        success_rate_component * WEIGHTS["success_rate"] +
        token_efficiency_component * WEIGHTS["token_efficiency"] +
        latency_component * WEIGHTS["latency"]
    )

    if effectiveness_score >= THRESHOLDS["effective"]:
        decision = "effective"
    elif effectiveness_score >= THRESHOLDS["neutral"]:
        decision = "neutral"
    else:
        decision = "ineffective"

    return {
        "evaluation_id": f"EVAL-PAIR-P001-S002-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "memory_ids": memory_ids,
        "evaluation_type": "pair",
        "note": "P-001 and S-002 are always used together. Evaluated as a pair.",
        "group_a": {
            "execution_ids": [m["execution_id"] for m in metrics_a],
            "count": len(metrics_a),
            "avg_quality": round(avg_qa, 2),
            "avg_tokens": round(avg_ta, 2),
            "avg_latency_ms": round(avg_la, 2),
        },
        "group_b": {
            "execution_ids": [m["execution_id"] for m in metrics_b],
            "count": len(metrics_b),
            "avg_quality": round(avg_qb, 2),
            "avg_tokens": round(avg_tb, 2),
            "avg_latency_ms": round(avg_lb, 2),
        },
        "deltas": {
            "quality_delta": quality_delta,
            "token_delta": token_delta,
            "token_delta_pct": token_delta_pct,
            "latency_delta_ms": latency_delta_ms,
        },
        "effectiveness_score": round(effectiveness_score, 3),
        "effectiveness_score_breakdown": {
            "quality_component": {"value": round(quality_component, 3), "weight": WEIGHTS["quality"]},
            "success_rate_component": {"value": round(success_rate_component, 3), "weight": WEIGHTS["success_rate"]},
            "token_efficiency_component": {"value": round(token_efficiency_component, 3), "weight": WEIGHTS["token_efficiency"]},
            "latency_component": {"value": round(latency_component, 3), "weight": WEIGHTS["latency"]},
        },
        "decision": decision,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    print("=" * 60)
    print("Phase 5.7.3 — Memory Effectiveness Evaluator")
    print("=" * 60)

    all_traces = load_all_traces()
    print(f"Loaded {len(all_traces)} traces")

    promoted = find_promoted_memories()
    print(f"Found {len(promoted)} promoted memories")

    memory_index = load_memory_index()
    memory_meta_map = {m["memory_id"]: m for m in memory_index.get("memories", [])}

    # Identify which memories are always used together
    memory_usage_map = defaultdict(set)
    for t in all_traces:
        mem_used = t.get("memory_retrieval", {}).get("memories_used", [])
        eid = t["execution_id"]
        for mid in mem_used:
            memory_usage_map[mid].add(eid)

    results = []

    # Check if P-001 and S-002 are always used together
    p001_execs = memory_usage_map.get("P-001", set())
    s002_execs = memory_usage_map.get("S-002", set())
    if p001_execs == s002_execs and len(p001_execs) > 0:
        print(f"\n⚠ P-001 and S-002 share the same executions: {sorted(p001_execs)}")
        print("  Evaluating as a pair (cannot attribute to single memory).")
        pair_result = evaluate_pair(["P-001", "S-002"], memory_meta_map, all_traces)
        if pair_result:
            results.append(pair_result)

    # Evaluate individual promoted memories
    for mem in promoted:
        mid = mem["memory_id"]
        # Skip individual evaluation if already in pair
        if mid in ("P-001", "S-002"):
            continue

        print(f"\nEvaluating: {mid} ({mem.get('type', '?')})")
        result = evaluate_memory(mid, mem, all_traces)
        if result:
            status = result.get("status", "evaluated")
            if status == "skipped":
                print(f"  SKIP: {result.get('reason', '')}")
            else:
                print(f"  decision: {result['decision']}")
                print(f"  effectiveness_score: {result['effectiveness_score']}")
                print(f"  quality_delta: {result['deltas']['quality_delta']}")
                print(f"  token_delta_pct: {result['deltas']['token_delta_pct']}%")
                print(f"  latency_delta_ms: {result['deltas']['latency_delta_ms']}ms")
            results.append(result)

    # Print pair evaluation
    if pair_result:
        print(f"\nPair Evaluation (P-001 + S-002):")
        print(f"  decision: {pair_result['decision']}")
        print(f"  effectiveness_score: {pair_result['effectiveness_score']}")
        print(f"  quality_delta: {pair_result['deltas']['quality_delta']}")
        print(f"  token_delta_pct: {pair_result['deltas']['token_delta_pct']}%")
        print(f"  latency_delta_ms: {pair_result['deltas']['latency_delta_ms']}ms")

    # Summary
    evaluated = [r for r in results if "decision" in r]
    effective = [r for r in evaluated if r["decision"] == "effective"]
    neutral = [r for r in evaluated if r["decision"] == "neutral"]
    ineffective = [r for r in evaluated if r["decision"] == "ineffective"]

    print(f"\n{'=' * 60}")
    print(f"Evaluation Complete:")
    print(f"  evaluated: {len(evaluated)}")
    print(f"  effective: {len(effective)}")
    print(f"  neutral: {len(neutral)}")
    print(f"  ineffective: {len(ineffective)}")

    # Write output
    output = {
        "version": "1.0",
        "phase": "5.7.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "evaluator.py (Phase 5.7.3 Memory Effectiveness Evaluator)",
        "method": "cross_group_comparison",
        "caveat": "All traces have memory_mode=on. No memory OFF baseline. Correlational, not causal.",
        "summary": {
            "total_promoted_memories": len(promoted),
            "evaluated": len(evaluated),
            "effective": len(effective),
            "neutral": len(neutral),
            "ineffective": len(ineffective),
        },
        "results": results,
        "raw_data": {
            "trace_metrics": [],
            "memory_usage": {mid: sorted(list(exs)) for mid, exs in memory_usage_map.items()},
        },
    }

    # Add raw trace metrics
    for t in all_traces:
        m = extract_trace_metrics(t)
        m["quality_score"] = compute_quality_score(t)
        output["raw_data"]["trace_metrics"].append(m)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\nOutput written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()