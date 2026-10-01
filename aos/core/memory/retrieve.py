"""Memory retrieval: deterministic relevance scoring + decay.

Ported from the original ``retrieval_optimizer`` with two fixes:

  - the memory index is the SQLite store, not a brute-forced YAML file
  - the decay factor is actually loaded from the store and applied (the
    original computed decay but never passed it into retrieval)

No embeddings, no network: scoring is metadata-driven and deterministic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from aos.core.memory.policy import load_policy
from aos.core.memory.store import MemoryStore, hypothesis_lane

# Default thresholds (overridable via content/policies/retrieval.json).
TOP_K = 5
MIN_SCORE = 0.15


def query_hash(query: dict[str, Any]) -> str:
    text = str(query.get("task_text", ""))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ── static relevance ───────────────────────────────────────────────────
def _is_matchable_tag(tag: str) -> bool:
    """Whether a tag is long enough to be trusted as a substring match.

    Three characters is a *Latin* heuristic: it keeps `id` and `to` from matching half
    the corpus, and Chinese words are normally two characters — 缓存, 配置, 排序. One
    rule for both scripts means Chinese tags are silently unmatchable, which is half of
    why a purely Chinese task recalls nothing (defect V).
    """
    if not tag:
        return False
    if any("\u4e00" <= char <= "\u9fff" for char in tag):
        return len(tag) >= 2
    return len(tag) >= 3


def compute_static_relevance(memory: dict[str, Any], query: dict[str, Any]) -> float:
    """Deterministic, metadata-driven relevance score (ported verbatim)."""
    category = memory.get("category", "")
    tags = [str(t).lower() for t in memory.get("tags", [])]
    mem_roles = [str(r).lower() for r in memory.get("roles", [])]

    q_category = str(query.get("category", "")).lower()
    q_domains = [str(d).lower() for d in query.get("domains", [])]
    q_roles = [str(r).lower() for r in query.get("roles", [])]
    q_keywords = [str(k).lower() for k in query.get("keywords", [])]

    task_text = str(query.get("task_text", "")).lower()
    task_text_score = 0.0
    if task_text and tags:
        task_tag_matches = 0
        for tag in tags:
            if _is_matchable_tag(tag) and tag in task_text:
                task_tag_matches += 1
        task_text_score = min(task_tag_matches * 0.20, 0.60)

    category_match = 1.0 if q_category and q_category in category.lower() else 0.0

    domain_match = 0.0
    if q_domains:
        domain_signal = 0
        for d in q_domains:
            if d in tags or d in category.lower():
                domain_signal += 1
        domain_match = domain_signal / max(len(q_domains), 1)

    role_match = 0.0
    if q_roles:
        role_signal = 0
        for r in q_roles:
            if r in mem_roles or r in tags:
                role_signal += 1
        role_match = role_signal / max(len(q_roles), 1)

    keyword_match = 0.0
    if q_keywords:
        kw_signal = 0
        for k in q_keywords:
            if k in tags or k in category.lower() or any(k in r for r in mem_roles):
                kw_signal += 1
        keyword_match = kw_signal / max(len(q_keywords), 1)

    mem_type = memory.get("type", "")
    type_boost = 0.0
    # A memory that says "not this" or "not beyond this line" is worth surfacing
    # for exactly the domain it would have hurt; one that says "do it this way"
    # only earns its place when the task spans several domains.
    if mem_type in ("failure", "constraint") and any(d in tags for d in q_domains):
        type_boost = 0.15
    elif mem_type == "procedural" and len(q_domains) >= 2:
        type_boost = 0.05

    relevance = (
        task_text_score * 0.40
        + category_match * 0.15
        + domain_match * 0.15
        + type_boost * 0.10
        + role_match * 0.10
        + keyword_match * 0.10
    )
    return round(relevance, 3)


# ── adaptive score ─────────────────────────────────────────────────────
def compute_adaptive_score(
    memory: dict[str, Any],
    static_relevance: float,
    usage: dict[str, Any],
    decay_factor: float,
    weights: dict[str, float],
    cap: float,
) -> dict[str, Any]:
    """Multiplicative score: static relevance dominates, quality only modifies."""
    memory_id = memory["memory_id"]
    # Read the rate the store derived, rather than recomputing it from
    # usage_count here: usage_count counts runs the memory was *in*, and most of
    # them may never have been judged. Dividing by it made an absent verdict look
    # like a failure.
    success_rate = float(usage.get("success_rate", 0.5))
    confidence_score = min(int(memory.get("observation_count", 0)) / 5.0, 1.0)

    quality_bonus = (
        success_rate * weights.get("success_rate", 0.15)
        + confidence_score * weights.get("confidence", 0.10)
    )
    quality_bonus = min(quality_bonus, cap)

    adaptive = static_relevance * (1.0 + quality_bonus)
    final_score = adaptive * decay_factor

    is_hypothesis = hypothesis_lane(memory, memory_id)
    return {
        "memory_id": memory_id,
        "static_relevance": round(static_relevance, 3),
        "success_rate": round(success_rate, 3),
        "confidence_score": round(confidence_score, 3),
        "quality_bonus": round(quality_bonus, 3),
        "adaptive_score": round(adaptive, 3),
        "decay_factor": round(decay_factor, 3),
        "final_score": round(final_score, 3),
        "evidence_level": memory.get("evidence_level", "hypothesis"),
        "confidence": memory.get("confidence", "low"),
        "type": memory.get("type", "unknown"),
        "lane": memory.get("lane", "hypothesis" if is_hypothesis else "standard"),
        "status": memory.get("status", ""),
        "scope": memory.get("scope", "global"),
        "category": memory.get("category", ""),
        "title": memory.get("title", ""),
        "body": memory.get("body", ""),
        # The trigger clause is the single most useful thing to inject: without
        # it a memory reads to the model as an unmotivated fact.
        "when_to_apply": memory.get("when_to_apply", ""),
        "tags": memory.get("tags", []),
        # Provenance, so a recalled memory can be traced back to what produced
        # it instead of being believed on the strength of having been stored.
        "source_task": memory.get("source_task", ""),
        "source_project": memory.get("source_project", ""),
        "source_session": memory.get("source_session", ""),
        "source_loop_id": memory.get("source_loop_id", ""),
        "created_at": memory.get("created_at", ""),
        "last_verified_at": memory.get("last_verified_at", ""),
        "revalidate_after": memory.get("revalidate_after", ""),
        "version": int(memory.get("version", 1) or 1),
        "supersedes": memory.get("supersedes", ""),
        "observation_count": int(memory.get("observation_count", 0)),
        "use_count": int(memory.get("use_count", 0)),
        "success_count": int(memory.get("success_count", 0)),
        "usage_count": int(usage.get("usage_count", 0)),
        # Runs this memory appeared in whose verdict was actually earned; the
        # denominator behind success_rate, and the number a reviewer should see
        # before trusting a success rate built on a single observation.
        "outcome_count": int(usage.get("outcome_count", 0)),
        "is_hypothesis": is_hypothesis,
        "warning": "Unvalidated hypothesis — not an established engineering rule" if is_hypothesis else None,
    }


# ── decay ──────────────────────────────────────────────────────────────
def _days_since(iso: str) -> Optional[int]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def compute_decay_factor(
    memory: dict[str, Any],
    usage: dict[str, Any],
    global_avg_quality: float,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Compute a decay factor in [0.5, 1.0]. Never deletes a memory."""
    memory_id = memory["memory_id"]
    uc = int(usage.get("usage_count", 0))
    success_rate = float(usage.get("success_rate", 0.5))
    observation_count = int(memory.get("observation_count", 0))

    factors: list[float] = []
    reasons: list[str] = []

    # Trigger 1: unused
    last_activity = usage.get("last_used") or usage.get("last_retrieved")
    if uc == 0:
        days = _days_since(memory.get("created_at", ""))
        if days is None:
            factors.append(policy["factor_mild"])
            reasons.append("unused: no usage data")
        else:
            factors.append(_unused_factor(days, policy, reasons, "creation"))
    elif last_activity:
        days = _days_since(last_activity)
        if days is not None:
            factors.append(_unused_factor(days, policy, reasons, "last activity"))

    # Trigger 2: low success rate
    if uc >= policy["low_success_min_uses"]:
        if success_rate < policy["low_success_severe"]:
            factors.append(0.5)
            reasons.append(f"low_success_severe: {success_rate}")
        elif success_rate < policy["low_success_moderate"]:
            factors.append(0.7)
            reasons.append(f"low_success_moderate: {success_rate}")
        elif success_rate < policy["low_success_mild"]:
            factors.append(0.9)
            reasons.append(f"low_success_mild: {success_rate}")

    # Trigger 3: low confidence (few observations)
    if observation_count == 0:
        factors.append(policy["low_confidence_zero_obs"])
        reasons.append("low_confidence: 0 observations")
    elif observation_count == 1:
        factors.append(policy["low_confidence_one_obs"])
        reasons.append("low_confidence: 1 observation")

    # Trigger 4: hypothesis protection
    if hypothesis_lane(memory, memory_id):
        days = _days_since(memory.get("created_at", ""))
        if days is None or days > policy["hypothesis_max_days"]:
            factors.append(policy["hypothesis_factor"])
            reasons.append("hypothesis: past protection window")

    # Trigger 5: low performance vs global average
    if uc >= 2 and global_avg_quality > 0:
        quality_scores = usage.get("quality_scores", [])
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        ratio = avg_quality / global_avg_quality
        if ratio < policy["low_performance_severe_ratio"]:
            factors.append(policy["low_performance_severe_factor"])
            reasons.append(f"low_performance: avg_quality={avg_quality:.2f} vs global={global_avg_quality:.2f}")
        elif ratio < policy["low_performance_mild_ratio"]:
            factors.append(policy["low_performance_mild_factor"])
            reasons.append(f"low_performance_mild: avg_quality={avg_quality:.2f} vs global={global_avg_quality:.2f}")

    decay_factor = min(factors) if factors else 1.0
    return {
        "memory_id": memory_id,
        "decay_factor": round(decay_factor, 3),
        "state": _decay_state(decay_factor),
        "reasons": reasons,
        "usage_count": uc,
        "success_rate": round(success_rate, 3),
        "observation_count": observation_count,
    }


def _decay_state(factor: float) -> str:
    """The lifecycle band a decay factor sits in."""
    if factor >= 0.9:
        return "active"
    if factor >= 0.5:
        return "degraded"
    return "archived_candidate"


def _unused_factor(days: int, policy: dict[str, Any], reasons: list[str], label: str) -> float:
    if days >= policy["unused_severe_days"]:
        reasons.append(f"unused_severe: {days}d since {label}")
        return policy["factor_severe"]
    if days >= policy["unused_moderate_days"]:
        reasons.append(f"unused_moderate: {days}d since {label}")
        return policy["factor_moderate"]
    if days >= policy["unused_mild_days"]:
        reasons.append(f"unused_mild: {days}d since {label}")
        return policy["factor_mild"]
    return 1.0


def compute_all_decay(store: MemoryStore) -> dict[str, Any]:
    """Lower every memory's decay for age and poor usage — never raise it.

    ``decay_factor`` has two writers: the promotion gate lowers it when a human
    approves a weaken, this pass lowers it for staleness and poor usage. Neither
    may lift what the other wrote, so the persisted value is the **lower** of the
    stored factor and the recomputed one. Assigning here is what once made
    ``aos memory refresh`` turn a three-times-weakened 0.512 back into the 0.85
    that its *current* statistics implied — a human decision evaporating in a
    recompute that had no idea it had ever happened.
    """
    policy = load_policy("decay")
    usage_stats = store.usage_stats()
    global_avg = store.global_avg_quality()

    results = []
    for memory in store.memories_for_scoring():
        usage = usage_stats.get(memory["memory_id"], {})
        result = compute_decay_factor(memory, usage, global_avg, policy)
        stored = float(memory.get("decay_factor", 1.0) or 1.0)
        combined = round(min(result["decay_factor"], stored), 3)
        if combined != stored:
            store.set_decay_factor(memory["memory_id"], combined)
        # Report what a reader will now find in the store, not what this pass
        # alone thought the memory deserved.
        result["decay_factor"] = combined
        result["state"] = _decay_state(combined)
        results.append(result)

    summary = {
        "total_memories": len(results),
        "active": sum(1 for r in results if r["state"] == "active"),
        "degraded": sum(1 for r in results if r["state"] == "degraded"),
        "archived_candidate": sum(1 for r in results if r["state"] == "archived_candidate"),
    }
    return {"summary": summary, "memories": results}


# ── retrieval ──────────────────────────────────────────────────────────
def retrieve(
    query: dict[str, Any],
    *,
    k: Optional[int] = None,
    store: Optional[MemoryStore] = None,
    loop_id: str = "",
    log: bool = True,
) -> dict[str, Any]:
    """Rank memories for a query and return the top-K results.

    ``query`` keys: task_text, category, domains, roles, keywords,
    exclude_hypothesis, exclude_memories.

    ``difficulty`` is deliberately not among them: the memories table keeps the
    column as review metadata, but no scoring term reads it, so passing it here
    changes nothing rather than silently changing the ranking.
    """
    owns_store = store is None
    store = store or MemoryStore()
    try:
        policy = load_policy("retrieval")
        top_k = int(k if k is not None else policy["top_k"])
        min_score = float(policy["min_score"])
        weights = policy["quality_bonus_weights"]
        cap = float(policy["quality_bonus_cap"])

        # Lifecycle and scope are filters at read time, not decorations on the
        # row. A memory the gate retired must not reach a prompt, and a fact
        # learned in another repository must not be offered as if it were local.
        # An unknown project gets *global* memories only — "we don't know where
        # we are" is not a licence to borrow another repository's facts.
        recall_statuses = [str(s) for s in policy.get("recall_statuses", ["active", "verified"])]
        scopes = ["global"]
        project = str(query.get("scope_project") or "").strip()
        if project:
            scopes.append(f"project:{project}")
        session = str(query.get("scope_session") or "").strip()
        if session:
            scopes.append(f"session:{session}")

        memories = store.memories_for_scoring(statuses=recall_statuses, scopes=scopes)
        if not memories:
            return {
                "query": query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_considered": 0,
                "after_filter": 0,
                "top_k": 0,
                "results": [],
                "error": "No memories in store",
            }

        usage_stats = store.usage_stats()
        decay = store.decay_factors()
        exclude_memories = set(query.get("exclude_memories", []))

        results = []
        for memory in memories:
            mid = memory["memory_id"]
            if hypothesis_lane(memory, mid) and query.get("exclude_hypothesis", False):
                continue
            if mid in exclude_memories:
                continue
            static_rel = compute_static_relevance(memory, query)
            result = compute_adaptive_score(
                memory,
                static_rel,
                usage_stats.get(mid, {}),
                decay.get(mid, 1.0),
                weights,
                cap,
            )
            # The threshold is about relevance; decay is about recency and track
            # record. Judging the threshold on the post-decay number let a memory at
            # the policy's own 0.5 floor drop out of recall while its status stayed
            # `active` — retired by arithmetic, invisibly to `doctor` and to the
            # queue. `evolve.py` says decay should make a memory quieter, not kill it:
            # so the gate reads the pre-decay score, and decay keeps deciding order.
            if result["adaptive_score"] < min_score:
                continue
            results.append(result)

        results.sort(key=lambda r: r["final_score"], reverse=True)
        top = results[:top_k]

        for r in top:
            reasons = []
            if r["static_relevance"] > 0.3:
                reasons.append(f"relevance={r['static_relevance']}")
            if r["success_rate"] > 0.5:
                reasons.append(f"success_rate={r['success_rate']}")
            if r["confidence_score"] > 0:
                reasons.append(f"confidence={r['confidence_score']}")
            if r["use_count"]:
                reasons.append(f"used={r['use_count']}/{r['success_count']}")
            if r["decay_factor"] < 1.0:
                reasons.append(f"decayed={r['decay_factor']}")
            r["match_reasons"] = reasons or ["default_match"]

        if log:
            qh = query_hash(query)
            for rank, r in enumerate(top, start=1):
                store.log_retrieval(
                    memory_id=r["memory_id"], score=r["final_score"], rank=rank, loop_id=loop_id, query_hash=qh
                )

        return {
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_considered": len(memories),
            "after_filter": len(results),
            "top_k": len(top),
            "results": top,
        }
    finally:
        if owns_store:
            store.close()
