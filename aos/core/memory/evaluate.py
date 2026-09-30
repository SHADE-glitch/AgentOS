"""Memory effectiveness evaluation.

Ported from the old ``evaluation/evaluator.py`` cross-group comparison, but
grounded in what the SQLite store actually holds. The old evaluator needed
full execution traces (tokens, latency, agent response); those no longer
exist, so this version compares loop outcomes for loops that used a memory
against loops that did not, on the two signals we do keep: quality score and
success rate.

``compute_quality_score`` is kept verbatim: it is a pure heuristic used to
grade an agent response, and callers that still have response text can reuse
it to produce the quality scores stored in observations.

The engine stopped calling it by default. It grades the *shape* of a response —
markdown headers, bullets, Chinese function words — not whether the work was
right, so a delegated run with an empty response could never clear the promotion
threshold while a confident-looking wrong one always did. That is why it reads as
weight ``0.00`` in :mod:`aos.core.outcome`: available to a host that wants it as
an input, never a verdict on its own.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Effectiveness thresholds (same scale as the original evaluator).
THRESHOLDS = {"effective": 0.7, "neutral": 0.4}

# Only these components are computable from stored observations. They are
# normalised to sum to 1 so the score keeps a 0..1 range.
WEIGHTS = {"quality": 0.6, "success_rate": 0.4}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def compute_quality_score(response: str) -> float:
    """Heuristic 0..5 quality score for an agent response (ported verbatim)."""
    response = response or ""

    comp = 0
    if re.search(r"#{1,3}\s", response):
        comp += 1
    if re.search(r"[-*]\s", response):
        comp += 1
    if "```" in response:
        comp += 1
    if len(re.findall(r"#{1,3}\s", response)) >= 3:
        comp += 1
    if len(response) > 100:
        comp += 1

    acc = 0
    tech_terms = [
        "API", "TLS", "AES", "JWT", "RBAC", "SQL", "RAG", "LLM",
        "cache", "token", "encrypt", "vector", "retrieval", "index",
        "OAuth", "HMAC", "SHA", "PCI", "DSS", "embedding", "chunking",
        "OCR", "Cross-Encoder", "Dense", "Sparse", "Redis", "MySQL",
        "数据库", "向量", "检索", "加密", "认证", "授权", "缓存",
        "分布式", "高并发", "索引", "查询", "性能", "安全",
    ]
    if any(t.lower() in response.lower() for t in tech_terms):
        acc += 1
    if re.search(r"(?:使用|采用|选择|推荐|基于|通过)", response):
        acc += 1
    if re.search(r"(?:实现|配置|部署|设置|构建|处理)", response):
        acc += 1
    if re.search(r"(?:因为|原因|由于|为了|确保|避免)", response):
        acc += 1
    if re.search(r"(?:具体|详细|明确)", response):
        acc += 1

    struct = 0
    if re.search(r"^\d+[\.、）)]\s", response, re.MULTILINE):
        struct += 1
    if re.search(r"^#{1,3}\s", response, re.MULTILINE):
        struct += 1
    if len(response.split("\n")) > 8:
        struct += 1
    if response.count("\n") > 5:
        struct += 1
    if len(response) > 100 and "\n\n" in response:
        struct += 1

    act = 0
    if re.search(r"(?:步骤|流程|Step|方法|方式)", response):
        act += 1
    if re.search(r"(?:建议|推荐|方案|策略|设计)", response):
        act += 1
    if re.search(r"(?:例如|示例|比如|如)", response):
        act += 1
    if re.search(r"(?:配置|参数|设置|兼容|注意)", response):
        act += 1
    if len(response) > 100:
        act += 1

    nov = 0
    if re.search(r"(?:数据库|向量|检索|索引|缓存|存储|查询)", response):
        nov += 1
    if re.search(r"(?:权衡|取舍|trade|利弊|对比|相比)", response, re.IGNORECASE):
        nov += 1
    if re.search(r"(?:边界|极端|边缘|corner|特殊|异常)", response, re.IGNORECASE):
        nov += 1
    if re.search(r"(?:优化|改进|提升|增强|加速)", response):
        nov += 1
    if len(response) > 200:
        nov += 1

    weighted = comp * 0.25 + acc * 0.30 + struct * 0.15 + act * 0.20 + nov * 0.10
    return round(weighted, 2)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _success_rate(observations: list[dict[str, Any]]) -> float:
    if not observations:
        return 0.0
    return sum(1 for o in observations if o.get("outcome") == "success") / len(observations)


def evaluate_memory(memory_id: str, store: Any) -> Optional[dict[str, Any]]:
    """Compare loop outcomes for loops that used *memory_id* against the rest.

    Returns ``None`` when there is nothing to compare (no usage, or every loop
    used the memory), so callers never read a meaningless delta.
    """
    observations = store.list_observations()
    # "Used" is linkage, read from where linkage is recorded. The per-memory
    # observation rows this used to scan are gone: they wrote a run's verdict
    # against every recalled memory, which is the inference this module is meant
    # to *test*, not assume.
    used_loops = {
        r["loop_id"] for r in store.list_retrievals(memory_id=memory_id) if r.get("loop_id")
    }
    # Only runs whose verdict was earned belong in either group. An unlabelled
    # run says nothing, and counting it as "the runs without this memory went
    # worse" would be inventing the very comparison this report exists to make.
    loop_level = [o for o in observations if not o.get("memory_id") and not o.get("needs_review")]
    group_a = [o for o in loop_level if o.get("loop_id") in used_loops]
    group_b = [o for o in loop_level if o.get("loop_id") not in used_loops]
    if not group_a or not group_b:
        return None

    quality_a, quality_b = _avg([float(o["quality_score"]) for o in group_a]), _avg(
        [float(o["quality_score"]) for o in group_b]
    )
    success_a, success_b = _success_rate(group_a), _success_rate(group_b)

    quality_delta = round(quality_a - quality_b, 3)
    success_delta = round(success_a - success_b, 3)

    quality_component = _clamp(quality_delta / 2.5 + 0.5)
    success_component = _clamp(success_delta / 0.5 + 0.5)
    score = quality_component * WEIGHTS["quality"] + success_component * WEIGHTS["success_rate"]

    if score >= THRESHOLDS["effective"]:
        decision = "effective"
    elif score >= THRESHOLDS["neutral"]:
        decision = "neutral"
    else:
        decision = "ineffective"

    return {
        "memory_id": memory_id,
        "group_a": {"loops": len(group_a), "avg_quality": round(quality_a, 3), "success_rate": round(success_a, 3)},
        "group_b": {"loops": len(group_b), "avg_quality": round(quality_b, 3), "success_rate": round(success_b, 3)},
        "deltas": {"quality_delta": quality_delta, "success_rate_delta": success_delta},
        "effectiveness_score": round(score, 3),
        "decision": decision,
    }


def evaluate_all(store: Any) -> list[dict[str, Any]]:
    """Evaluate every memory that has appeared in at least one judged run."""
    # The candidate set comes from judged linkage, not from per-memory
    # observation rows — those no longer exist, and a reader that still looked
    # for them would report "0 evaluated" forever without failing.
    memory_ids = sorted(store.linkage_by_memory())
    evaluations = []
    for memory_id in memory_ids:
        result = evaluate_memory(memory_id, store)
        if result:
            evaluations.append(result)
    return evaluations


def summarize(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"effective": 0, "neutral": 0, "ineffective": 0}
    for evaluation in evaluations:
        counts[evaluation["decision"]] += 1
    return {"evaluated": len(evaluations), **counts}
