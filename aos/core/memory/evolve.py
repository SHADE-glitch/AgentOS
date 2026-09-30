"""The learning pipeline: observations -> candidates -> validation -> gate.

This is the "evolve" step of the loop. It ports the old
collector/validator/promoter chain into one place, with the safety property
the old system lacked: **nothing that is a hypothesis, or rests on weak
evidence, is ever promoted automatically**. Those cases are written to
``learning_reviews`` with ``status = 'pending'`` and wait for a human
``aos review approve <id>``.

Only memories that already carry strong, independent, quality-checked
evidence — and that do not conflict with another memory — are applied
directly. Every threshold comes from ``policy.py`` so it can be tuned with a
``content/policies/*.json`` file instead of being a scattered constant.
"""

from __future__ import annotations

from typing import Any, Optional

from aos.core.memory import conflict as conflict_mod
from aos.core.memory import evaluate as evaluate_mod
from aos.core.memory.policy import load_policy
from aos.core.memory.store import (
    MemoryStore,
    _now as _timestamp,
    hypothesis_lane,
)

# Candidate change types. ``success``/``failure`` are accepted because
# ``record.py`` emits them; they mean reinforce/weaken respectively.
WEAKEN_TYPES = frozenset({"weaken", "failure", "weaken_hypothesis"})

# Evidence levels ordered weakest to strongest.
EVIDENCE_LEVELS = (
    "hypothesis",
    "benchmark_evaluated",
    "runtime_validated",
    "independent_validated",
    "real_project_validated",
    "production_validated",
)
# Levels strong enough to be trusted without a human in the loop.
STRONG_EVIDENCE = frozenset(
    {"runtime_validated", "independent_validated", "real_project_validated", "production_validated"}
)


# ── grouping ───────────────────────────────────────────────────────────
def group_candidates(
    candidates: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Group candidates by the memory they target, gathering their evidence.

    Independent executions are counted as distinct loops that produced an
    observation for the target memory — the store-native equivalent of the
    old ``source_execution`` / observation-log counting.
    """
    obs_by_memory: dict[str, list[dict[str, Any]]] = {}
    for obs in observations:
        if obs.get("memory_id"):
            obs_by_memory.setdefault(obs["memory_id"], []).append(obs)

    groups: dict[str, dict[str, Any]] = {}

    def _group(memory_id: str) -> dict[str, Any]:
        return groups.setdefault(
            memory_id,
            {
                "memory_id": memory_id,
                "candidates": [],
                "executions": set(),
                "quality_scores": [],
                "source_hashes": set(),
                "best_quality": 0.0,
                "best_candidate_id": None,
            },
        )

    for candidate in candidates:
        for target in _targets_for(candidate):
            group = _group(target)
            group["candidates"].append(candidate)

            # Every observation of the target memory is an independent
            # execution, regardless of which loop produced the candidate.
            for obs in obs_by_memory.get(target, []):
                group["executions"].add(obs["loop_id"])
                if obs.get("source_hash"):
                    group["source_hashes"].add(obs["source_hash"])

            quality = float((candidate.get("payload") or {}).get("quality_score") or 0.0)
            group["quality_scores"].append(quality)
            if quality > group["best_quality"]:
                group["best_quality"] = quality
                group["best_candidate_id"] = candidate.get("candidate_id")

    return groups


def _targets_for(candidate: dict[str, Any]) -> list[str]:
    """The memories a candidate proposes to change."""
    target = candidate.get("target_memory") or ""
    if target:
        return [target]
    payload = candidate.get("payload") or {}
    return [m for m in (payload.get("memories_used") or []) if m]


# ── validation ─────────────────────────────────────────────────────────
def validate_group(
    group: dict[str, Any],
    *,
    promotion: dict[str, Any],
    rejection: dict[str, Any],
    memory: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the promotion rules to one memory's candidate group.

    Returns a result whose ``status`` is one of ``validated`` (strong enough
    to apply), ``hypothesis`` (real but unproven), ``review`` (must be seen by
    a human) or ``rejected`` (insufficient evidence — gather more and retry).
    """
    memory_id = group["memory_id"]
    is_hypothesis = hypothesis_lane(memory, memory_id)
    candidate_types = {c.get("candidate_type", "") for c in group["candidates"]}
    runs = len(group["executions"])
    best_quality = group["best_quality"]
    quality_threshold = float(promotion["quality_threshold"])
    required = int(
        promotion["hypothesis_min_observations"] if is_hypothesis else promotion["min_observations"]
    )

    checks = {
        "is_real_execution": runs >= 1,
        "has_execution_evidence": len(group["source_hashes"]) > 0,
        "quality_above_threshold": best_quality >= quality_threshold,
        "has_independent_verification": runs >= required,
        "not_hypothesis_candidate": "create_hypothesis" not in candidate_types or is_hypothesis,
    }

    def result(status: str, reason: Optional[str] = None) -> dict[str, Any]:
        confidence = min(runs / 5, 1.0) if not is_hypothesis else min(min(runs, 2) / 5, 1.0)
        return {
            "memory_id": memory_id,
            "candidate_id": group["best_candidate_id"],
            "candidate_types": sorted(t for t in candidate_types if t),
            "status": status,
            "validation_runs": runs,
            "quality_score": best_quality,
            "confidence": round(confidence, 3),
            "checks": checks,
            "rejection_reason": reason,
            "evidence_sources": sorted(group["executions"]),
            "memory_exists": memory is not None,
        }

    # Fail-closed type confusion: a hypothesis lane and a normal lane must not mix.
    if is_hypothesis and (candidate_types & {"reinforce", "success"}):
        return result("rejected", "type confusion: reinforce candidate targets a hypothesis memory")
    if not is_hypothesis and (candidate_types & {"reinforce_hypothesis", "weaken_hypothesis"}):
        return result(
            "rejected",
            "type confusion: hypothesis candidate targets a non-hypothesis memory",
        )

    # Hard evidence requirements.
    if not checks["is_real_execution"]:
        return result("rejected", "no independent execution observed for this memory")
    if not checks["has_execution_evidence"]:
        return result("rejected", "missing execution evidence (source_hash)")
    if not checks["quality_above_threshold"]:
        return result(
            "rejected",
            f"best quality {best_quality} below threshold {quality_threshold}",
        )
    if not checks["has_independent_verification"]:
        return result(
            "rejected",
            f"only {runs} observation(s); need >= {required} independent executions",
        )

    # Things a human must always see, never auto-applied.
    if "create_hypothesis" in candidate_types and not is_hypothesis:
        return result("review", "hypothesis candidates are held for human review")
    if candidate_types & WEAKEN_TYPES and rejection.get("reject_weaken", True):
        return result("review", "weaken candidates require human review")
    if is_hypothesis:
        if runs >= int(promotion["min_observations"]):
            return result("validated")
        return result("hypothesis")

    return result("validated")


# ── promotion ──────────────────────────────────────────────────────────
def _next_evidence_level(old_level: str, runs: int) -> str:
    if old_level in ("hypothesis", "benchmark_evaluated") and runs >= 1:
        return "runtime_validated"
    if old_level == "runtime_validated" and runs >= 2:
        return "independent_validated"
    return old_level


def _confidence_for(old_confidence: str, observations: int) -> str:
    if observations >= 5:
        return "high"
    if observations >= 2:
        return "medium"
    return old_confidence


def apply_promotion(result: dict[str, Any], store: MemoryStore) -> dict[str, Any]:
    """Write a validated result's evidence upgrade into the memory store."""
    memory_id = result["memory_id"]
    memory = store.get_memory(memory_id)
    if memory is None:
        return {"memory_id": memory_id, "status": "rejected", "reason": "memory not found"}

    runs = int(result["validation_runs"])
    old_level = memory.get("evidence_level", "hypothesis")
    old_confidence = memory.get("confidence", "low")
    old_status = memory.get("status", "active")

    new_level = _next_evidence_level(old_level, runs)
    new_observations = max(int(memory.get("observation_count", 0)), runs)
    new_confidence = _confidence_for(old_confidence, new_observations)
    # The gate's own verdict is `validated`; the memory's lifecycle state for
    # "strong evidence reached" is `verified`. Keeping them distinct is what
    # lets `status` drive recall while the review history stays readable.
    newly_verified = new_level in STRONG_EVIDENCE
    new_status = "verified" if newly_verified else old_status

    updates: dict[str, Any] = {
        "evidence_level": new_level,
        "confidence": new_confidence,
        "status": new_status,
        "observation_count": new_observations,
        # Promotion is exactly the event that renews a memory's verification
        # date, so it is stamped here and nowhere else.
        "last_verified_at": _timestamp() if newly_verified else memory.get("last_verified_at", ""),
        # Leaving the hypothesis lane is a one-way move made by evidence, not
        # by an author declaring it; a promoted memory is no longer a hint.
        "lane": "standard" if newly_verified else memory.get("lane", "standard"),
    }
    store.update_memory_fields(memory_id, **{k: v for k, v in updates.items() if v != ""})
    return {
        "memory_id": memory_id,
        "status": "applied",
        "evidence_level": {"old": old_level, "new": new_level},
        "confidence": {"old": old_confidence, "new": new_confidence},
        "status_field": {"old": old_status, "new": new_status},
        "observation_count": {"old": memory.get("observation_count", 0), "new": new_observations},
    }


def _can_auto_promote(
    result: dict[str, Any],
    memory: Optional[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> bool:
    """A promotion may skip the human gate only if it is strong and clean."""
    if result["status"] != "validated":
        return False
    if memory is None or conflicts:
        return False
    if hypothesis_lane(memory, result["memory_id"]):
        return False
    if memory.get("evidence_level") not in STRONG_EVIDENCE:
        return False
    return True


def _proposed_change(result: dict[str, Any], memory: Optional[dict[str, Any]]) -> dict[str, Any]:
    old_level = (memory or {}).get("evidence_level", "hypothesis")
    old_confidence = (memory or {}).get("confidence", "low")
    runs = int(result["validation_runs"])
    observations = max(int((memory or {}).get("observation_count", 0)), runs)
    return {
        "candidate_types": result["candidate_types"],
        "evidence_level": {"old": old_level, "new": _next_evidence_level(old_level, runs)},
        "confidence": {"old": old_confidence, "new": _confidence_for(old_confidence, observations)},
        "observation_count": {"old": (memory or {}).get("observation_count", 0), "new": observations},
    }


def _create_review(
    group: dict[str, Any], result: dict[str, Any], memory: Optional[dict[str, Any]], store: MemoryStore
) -> Optional[int]:
    """Open a pending review, unless one is already open for this memory."""
    memory_id = result["memory_id"]
    if store.has_pending_review(memory_id):
        return None
    evidence = {
        "validation_runs": result["validation_runs"],
        "quality_score": result["quality_score"],
        "confidence": result["confidence"],
        "candidate_types": result["candidate_types"],
        "evidence_sources": result["evidence_sources"],
        "checks": result["checks"],
        "reason": result["rejection_reason"],
        "conflicts": result.get("conflicts", []),
    }
    return store.add_review(
        memory_id=memory_id,
        candidate_id=result["candidate_id"],
        proposed_change=_proposed_change(result, memory),
        evidence=evidence,
    )


# ── the pipeline ───────────────────────────────────────────────────────
def run_learning(*, store: Optional[MemoryStore] = None, apply: bool = True) -> dict[str, Any]:
    """Run one learning cycle over the store's candidates and observations."""
    owns_store = store is None
    store = store or MemoryStore()
    try:
        promotion = load_policy("promotion")
        rejection = load_policy("rejection")
        candidates = store.list_candidates()
        observations = store.list_observations()
        memories = {m["memory_id"]: m for m in store.memories_for_scoring()}

        groups = group_candidates(candidates, observations)
        results: list[dict[str, Any]] = []
        reviews_created = 0
        promoted: list[dict[str, Any]] = []

        for memory_id in sorted(groups):
            group = groups[memory_id]
            memory = memories.get(memory_id)
            result = validate_group(
                group, promotion=promotion, rejection=rejection, memory=memory
            )
            result["conflicts"] = (
                conflict_mod.conflicts_for(memory_id, list(memories.values())) if memory else []
            )
            result["gate"] = None
            result["review_id"] = None
            result["promotion"] = None

            if result["status"] in ("validated", "hypothesis"):
                if _can_auto_promote(result, memory, result["conflicts"]):
                    result["gate"] = "auto"
                    if apply:
                        result["promotion"] = apply_promotion(result, store)
                        promoted.append(result["promotion"])
                else:
                    result["gate"] = "review"
                    review_id = _create_review(group, result, memory, store)
                    if review_id is not None:
                        result["review_id"] = review_id
                        reviews_created += 1
            elif result["status"] == "review":
                result["gate"] = "review"
                review_id = _create_review(group, result, memory, store)
                if review_id is not None:
                    result["review_id"] = review_id
                    reviews_created += 1
            else:
                store.add_event(
                    event_type="learning.rejected",
                    payload={"memory_id": memory_id, "reason": result["rejection_reason"]},
                )

            results.append(result)

        evaluations = evaluate_mod.summarize(evaluate_mod.evaluate_all(store))
        summary = {
            "candidates": len(candidates),
            "memory_groups": len(groups),
            "promoted": len(promoted),
            "reviews_created": reviews_created,
            "rejected": sum(1 for r in results if r["status"] == "rejected"),
            "pending_reviews": len(store.list_reviews(status="pending")),
            "evaluations": evaluations,
        }
        store.add_event(event_type="learning.run", payload=summary)
        return {"summary": summary, "results": results, "promotions": promoted}
    finally:
        if owns_store:
            store.close()


# ── review gate ────────────────────────────────────────────────────────
def list_reviews(*, store: Optional[MemoryStore] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
    owns_store = store is None
    store = store or MemoryStore()
    try:
        return store.list_reviews(status=status)
    finally:
        if owns_store:
            store.close()


def approve_review(review_id: int, *, store: Optional[MemoryStore] = None) -> dict[str, Any]:
    """Approve a pending review and apply its promotion to the memory."""
    owns_store = store is None
    store = store or MemoryStore()
    try:
        review = store.get_review(review_id)
        if review is None:
            return {"review_id": review_id, "status": "not_found"}
        if review["status"] != "pending":
            return {"review_id": review_id, "status": "already_decided", "review_status": review["status"]}

        evidence = review.get("evidence", {})
        result = {
            "memory_id": review["memory_id"],
            "validation_runs": int(evidence.get("validation_runs", 0)),
            "quality_score": float(evidence.get("quality_score", 0.0)),
            "candidate_types": evidence.get("candidate_types", []),
        }
        promotion = apply_promotion(result, store)
        store.set_review_status(review_id, "approved")
        store.add_event(
            event_type="learning.review_approved",
            payload={"review_id": review_id, "memory_id": review["memory_id"]},
        )
        return {"review_id": review_id, "status": "approved", "promotion": promotion}
    finally:
        if owns_store:
            store.close()


def reject_review(review_id: int, *, store: Optional[MemoryStore] = None) -> dict[str, Any]:
    """Reject a pending review; the memory is left untouched."""
    owns_store = store is None
    store = store or MemoryStore()
    try:
        review = store.get_review(review_id)
        if review is None:
            return {"review_id": review_id, "status": "not_found"}
        if review["status"] != "pending":
            return {"review_id": review_id, "status": "already_decided", "review_status": review["status"]}
        store.set_review_status(review_id, "rejected")
        store.add_event(
            event_type="learning.review_rejected",
            payload={"review_id": review_id, "memory_id": review["memory_id"]},
        )
        return {"review_id": review_id, "status": "rejected", "memory_id": review["memory_id"]}
    finally:
        if owns_store:
            store.close()
