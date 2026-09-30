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

from aos.core.learning import dedupe as dedupe_mod
from aos.core.memory import conflict as conflict_mod
from aos.core.memory import evaluate as evaluate_mod
from aos.core.memory.policy import load_policy
from aos.core.memory.record import (
    PROPOSAL_TYPES,
    add_candidates_for_memories,
    candidate_type_for,
    memories_of_loop,
    proposal_for_loop,
    should_propose,
)
from aos.core.memory.store import (
    MemoryStore,
    _now as _timestamp,
    hypothesis_lane,
)
from aos.core.outcome import OUTCOMES

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
    candidates: list[dict[str, Any]], linkage: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """Group candidates by the memory they target, gathering their evidence.

    ``linkage`` maps a memory to the runs it was recalled into **whose verdict was
    earned** (``store.linkage_by_memory``). Independent executions are counted from
    those distinct loops.

    This used to be counted from per-memory observation rows, which were written
    for every recalled memory whether or not anybody judged the run — so the gate
    was measuring how often a memory showed up, and calling that evidence.
    """
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
        is_proposal = candidate.get("candidate_type") in PROPOSAL_TYPES
        for target in _targets_for(candidate):
            group = _group(target)
            group["candidates"].append(candidate)

            for run in linkage.get(target, []):
                group["executions"].add(run["loop_id"])
                if run.get("source_hash"):
                    group["source_hashes"].add(run["source_hash"])

            # A proposal has no memory to have been observed against, so the run
            # that drafted it is its only execution. Counting it for a memory that
            # exists would let a candidate manufacture its own evidence.
            if is_proposal:
                loop_id = candidate.get("loop_id") or ""
                if loop_id:
                    group["executions"].add(loop_id)
                source_hash = (candidate.get("payload") or {}).get("source_hash") or ""
                if source_hash:
                    group["source_hashes"].add(source_hash)

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
    proposal = _proposal_of(group) if memory is None else None
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
            "proposal": proposal,
        }

    # A proposal is a different question from a promotion. Nothing about it can be
    # settled by counting observations, because the memory does not exist yet: the
    # evidence requirement is that a real run happened, and the decision is a
    # human's. This branch comes before the thresholds because `quality_threshold`
    # measures "was this good enough to trust again", which is not what a first
    # episode — least of all a failed one — is being asked.
    if memory is None and proposal is not None:
        if not checks["is_real_execution"]:
            return result("rejected", "the proposal has no execution behind it")
        if not checks["has_execution_evidence"]:
            return result("rejected", "proposal has no execution evidence (source_hash)")
        if not rejection.get("hypothesis_requires_review", True):
            return result("validated")
        return result("review", "a new memory is written only by a human decision")

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
    # A weakening group is not asking for more trust, so the quality bar that
    # guards trust does not apply to it. Holding a failure report to "was the work
    # good?" is how negative learning could never start.
    if not checks["quality_above_threshold"] and not (candidate_types & WEAKEN_TYPES):
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
    if candidate_types & WEAKEN_TYPES and candidate_types & {"reinforce", "success"}:
        # Checked before the plain weakening case: a contradiction is a different
        # question from a demotion, and the reviewer has to be told which one they
        # are answering.
        return result(
            "review",
            "this memory has both reinforcing and weakening evidence; a human picks",
        )
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


# Evidence levels, strongest to weakest, for the negative direction. A memory that
# keeps turning up in failed runs has to be able to *lose* standing: until now the
# gate could only ever raise it, which is one way a store grows more confident
# while getting worse.
_PREV_EVIDENCE_LEVEL = {
    level: EVIDENCE_LEVELS[index - 1] if index > 0 else level
    for index, level in enumerate(EVIDENCE_LEVELS)
}
_CONFIDENCE_ORDER = ("low", "medium", "high")
# How much a confirmed failure costs a memory's ranking, and the floor under it.
# The floor exists because `deprecated` is the state that retires a memory; decay
# is only supposed to make it quieter, not to kill it by arithmetic.
#
# NOTE for the usage-feedback phase: `decay_factor` has a second writer (the
# recency/usage decay), and it must combine with this penalty by taking the lower
# of the two, not recompute from scratch — otherwise every decay pass silently
# undoes every recorded failure.
_WEAKEN_DECAY_FACTOR = 0.8
_MIN_DECAY_AFTER_WEAKEN = 0.5


def _prev_evidence_level(old_level: str) -> str:
    return _PREV_EVIDENCE_LEVEL.get(old_level, old_level)


def _lower_confidence(old_confidence: str) -> str:
    index = _CONFIDENCE_ORDER.index(old_confidence) if old_confidence in _CONFIDENCE_ORDER else 0
    return _CONFIDENCE_ORDER[max(0, index - 1)]


def _proposal_of(group: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The drafted memory a ``create`` candidate is proposing, if this group has one."""
    for candidate in group.get("candidates", []):
        if candidate.get("candidate_type") in PROPOSAL_TYPES:
            payload = candidate.get("payload") or {}
            if payload.get("body") or payload.get("title"):
                return payload
    return None


def decide_promotion(
    result: dict[str, Any], memory: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """What approving this group would do, worked out once and as data.

    Both the review (which has to show a human the consequence) and the write
    (which has to perform it) read this, so they cannot drift apart — the old
    gate showed an upgrade and applied an upgrade even when the candidates were
    asking for the memory to be weakened.

    ``kind`` is one of ``reinforce`` / ``weaken`` / ``create`` / ``mixed``.
    """
    types = set(result.get("candidate_types") or [])
    weakens = bool(types & WEAKEN_TYPES)
    reinforces = bool(types & {"reinforce", "success", "reinforce_hypothesis"})
    creates = bool(types & PROPOSAL_TYPES)
    runs = int(result.get("validation_runs", 0))
    # `observation_count` is an input to the judgement (how much has this memory
    # actually been through) and never an output: the record path owns that
    # counter. Writing it here would give one column two writers and make every
    # review unapprovable, because a memory that got used again between being
    # filed and being read would no longer match its own baseline.
    observations = max(int((memory or {}).get("observation_count", 0)), runs)

    if creates and memory is None:
        proposal = result.get("proposal") or {}
        return {
            "kind": "create",
            "memory_id": result["memory_id"],
            "reason": "a new memory is written only by a human decision",
            # A proposal becomes an *active* memory whose evidence is still one
            # run: approval is about worth-remembering, not about proven.
            "changes": {
                "status": "active",
                "evidence_level": "hypothesis",
                "confidence": "low",
                "lane": "hypothesis",
            },
            "before": {},
            "proposal": proposal,
        }

    current = memory or {}
    old_level = current.get("evidence_level", "hypothesis")
    old_confidence = current.get("confidence", "low")
    old_status = current.get("status", "active")
    old_decay = float(current.get("decay_factor", 1.0) or 1.0)

    if weakens and reinforces:
        # Contradictory evidence. A human is asked to adjudicate, and approving
        # means "keep it, note the disagreement" — not silently picking one side.
        return {
            "kind": "mixed",
            "memory_id": result["memory_id"],
            "reason": "reinforcing and weakening evidence both exist; approval records "
                      "the decision and leaves the evidence level where it is",
            "changes": {},
            "before": {"evidence_level": old_level, "confidence": old_confidence,
                       "status": old_status},
        }

    if weakens:
        new_level = _prev_evidence_level(old_level)
        # Falling off the bottom of the ladder, or being weakened twice from the
        # hypothesis lane, is what retirement means. It is a status change, not a
        # delete: the provenance stays, and the memory stops being recalled.
        already_weak = old_level == "hypothesis" or current.get("status") == "deprecated"
        new_status = "deprecated" if already_weak else old_status
        return {
            "kind": "weaken",
            "memory_id": result["memory_id"],
            "reason": "the runs it appeared in failed",
            "changes": {
                "evidence_level": new_level,
                "confidence": _lower_confidence(old_confidence),
                "status": new_status,
                "decay_factor": round(max(_MIN_DECAY_AFTER_WEAKEN, old_decay * _WEAKEN_DECAY_FACTOR), 4),
            },
            "before": {"evidence_level": old_level, "confidence": old_confidence,
                       "status": old_status, "decay_factor": old_decay},
        }

    new_level = _next_evidence_level(old_level, runs)
    newly_verified = new_level in STRONG_EVIDENCE
    return {
        "kind": "reinforce",
        "memory_id": result["memory_id"],
        "reason": "the runs it appeared in succeeded",
        "changes": {
            "evidence_level": new_level,
            "confidence": _confidence_for(old_confidence, observations),
            # The gate's own verdict is `validated`; the memory's lifecycle state
            # for "strong evidence reached" is `verified`. Keeping them distinct is
            # what lets `status` drive recall while the review history stays legible.
            "status": "verified" if newly_verified else old_status,
            # Promotion is the event that renews a verification date, so it is
            # stamped here and nowhere else.
            "last_verified_at": _timestamp() if newly_verified else current.get("last_verified_at", ""),
            # Leaving the hypothesis lane is earned by evidence, never declared.
            "lane": "standard" if newly_verified else current.get("lane", "standard"),
        },
        "before": {"evidence_level": old_level, "confidence": old_confidence,
                   "status": old_status},
    }


def apply_effect(store: MemoryStore, *, memory_id: str, effect: dict[str, Any]) -> dict[str, Any]:
    """Write an effect exactly as it was decided, or refuse to write anything.

    The effect arrives as data — the same data a review showed a human — and is
    applied verbatim. Two cases make it refuse: the memory does not exist, or it
    no longer looks like the row the decision was taken against (checked field by
    field against ``before``). Writing over a memory that moved while its review
    sat in the queue would make the approval mean something nobody agreed to.
    """
    kind = effect.get("kind") or "reinforce"
    changes = {k: v for k, v in (effect.get("changes") or {}).items() if v != ""}
    before = effect.get("before") or {}
    memory = store.get_memory(memory_id)

    if kind == "create":
        if memory is not None:
            return {
                "memory_id": memory_id,
                "status": "stale",
                "reason": "a memory with this id already exists",
            }
        proposal = effect.get("proposal") or {}
        if not proposal:
            return {"memory_id": memory_id, "status": "rejected", "reason": "proposal payload is gone"}
        store.upsert_memory(
            {
                "memory_id": memory_id,
                "type": proposal.get("type") or "episodic",
                "category": proposal.get("category") or "",
                "title": proposal.get("title") or "",
                "body": proposal.get("body") or "",
                "scope": proposal.get("scope") or "global",
                "when_to_apply": proposal.get("when_to_apply") or "",
                "source_task": proposal.get("task_id") or "",
                "source_session": proposal.get("session_id") or "",
                "source_project": proposal.get("cwd") or "",
                "source_loop_id": proposal.get("loop_id") or "",
                **changes,
            },
            tags=proposal.get("tags") or [],
            roles=proposal.get("roles") or [],
        )
        return {
            "memory_id": memory_id,
            "status": "created",
            "kind": "create",
            "type": proposal.get("type"),
            "title": proposal.get("title"),
            "evidence_level": {"old": None, "new": changes.get("evidence_level")},
            "status_field": {"old": None, "new": changes.get("status")},
        }

    if memory is None:
        return {"memory_id": memory_id, "status": "rejected", "reason": "memory not found"}

    drifted = {
        key: {"was": value, "now": memory.get(key)}
        for key, value in before.items()
        if memory.get(key) != value
    }
    if drifted:
        return {
            "memory_id": memory_id,
            "status": "stale",
            "reason": "the memory changed after this decision was made; run learning again",
            "drifted": drifted,
        }

    if not changes:
        # Contradictory evidence: the human said "keep it". Nothing about the
        # memory changes, and that is the whole content of the decision — writing
        # something here would be the gate inventing a conclusion.
        return {
            "memory_id": memory_id,
            "status": "recorded",
            "kind": kind,
            "reason": effect.get("reason", ""),
        }

    store.update_memory_fields(memory_id, **changes)
    return {
        "memory_id": memory_id,
        "status": "applied",
        "kind": kind,
        "evidence_level": {"old": before.get("evidence_level"), "new": changes.get("evidence_level")},
        "confidence": {"old": before.get("confidence"), "new": changes.get("confidence")},
        "status_field": {"old": before.get("status"), "new": changes.get("status")},
        "decay_factor": {"old": before.get("decay_factor"), "new": changes.get("decay_factor")},
    }


def apply_promotion(result: dict[str, Any], store: MemoryStore) -> dict[str, Any]:
    """Decide and apply in one step: the automatic path's whole effect."""
    effect = decide_promotion(result, store.get_memory(result["memory_id"]))
    return apply_effect(store, memory_id=result["memory_id"], effect=effect)


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
    # Anything that asks to *remove* standing, or asks for a brand new memory, is
    # a human decision by construction. Auto-weakening would let one bad run demote
    # a memory nobody chose, and auto-creating would let the loop write itself.
    types = set(result.get("candidate_types") or [])
    if types & PROPOSAL_TYPES or types & WEAKEN_TYPES:
        return False
    return True


def _proposed_change(result: dict[str, Any], memory: Optional[dict[str, Any]]) -> dict[str, Any]:
    """What approving this review will do, in the reviewer's own terms.

    Derived from :func:`decide_promotion`, the same function the write calls, so
    a review can never promise an upgrade and deliver one anyway.
    """
    decision = decide_promotion(result, memory)
    return {
        "kind": decision["kind"],
        "candidate_types": result["candidate_types"],
        "reason": decision["reason"],
        "changes": decision["changes"],
        "before": decision["before"],
    }


def _open_conflict_review(
    store: MemoryStore, group: dict[str, Any], verdict: dict[str, Any], proposal: dict[str, Any]
) -> tuple[Optional[int], bool]:
    """Ask a person which of two similar statements is the one to keep.

    The grey band is deliberately not resolved by code: merging on a 0.7 ratio
    would silently delete a fact nobody agreed to lose, and keeping both lets the
    store fill with near-duplicates. So the pair goes to the queue with its
    numbers attached, approving means "the new one supersedes the old", and
    rejecting means the opposite.
    """
    existing = verdict["match"]
    existing_id = str(existing["memory_id"])
    pending = store.pending_review_id(existing_id, kind="conflict")
    if pending is not None:
        return pending, False
    loops = sorted(group["executions"])
    review_id = store.add_review(
        memory_id=existing_id,
        candidate_id=group["best_candidate_id"],
        kind="conflict",
        loop_id=group["candidates"][0].get("loop_id", "") if group.get("candidates") else "",
        proposed_change={
            "kind": "conflict",
            "action": "supersede",
            "supersedes": existing_id,
            # Only the words that will actually be written. `status`, `lane`,
            # `evidence_level` and `confidence` are set by _resolve_conflict itself,
            # so copying the proposal's claims into the effect would let the review
            # advertise a standing the write never grants.
            "new": {
                key: proposal.get(key)
                for key in (
                    "memory_id", "type", "category", "title", "body", "tags", "roles",
                    "scope", "when_to_apply",
                )
            },
        },
        evidence={
            "reason": "possible duplicate, similarity in the grey band",
            "ratio": existing["ratio"],
            "tag_jaccard": existing["tag_jaccard"],
            "existing": {"memory_id": existing_id, "title": existing.get("title", ""),
                         "status": existing.get("status", "")},
            "proposed": {"title": proposal.get("title", ""), "body": proposal.get("body", "")},
            "evidence_sources": loops,
        },
    )
    return review_id, True


def _create_review(
    group: dict[str, Any], result: dict[str, Any], memory: Optional[dict[str, Any]], store: MemoryStore
) -> tuple[Optional[int], bool]:
    """Open a pending review, or return the one already open for this memory.

    The second value says whether this call created it: a cycle that reuses an
    open review must not report a new one, or the queue looks like it is growing
    when it is only being re-described.
    """
    memory_id = result["memory_id"]
    existing = store.pending_review_id(memory_id, kind="promotion")
    if existing is not None:
        return existing, False
    evidence = {
        "validation_runs": result["validation_runs"],
        "quality_score": result["quality_score"],
        "confidence": result["confidence"],
        "candidate_types": result["candidate_types"],
        "evidence_sources": result["evidence_sources"],
        "checks": result["checks"],
        "reason": result["rejection_reason"],
        "conflicts": result.get("conflicts", []),
        # A create review has to carry the words being approved: the memory does
        # not exist yet, so there is nothing else for the reviewer to read.
        "proposal": result.get("proposal"),
    }
    review_id = store.add_review(
        memory_id=memory_id,
        candidate_id=result["candidate_id"],
        proposed_change=_proposed_change(result, memory),
        evidence=evidence,
        kind="promotion",
    )
    return review_id, True


# ── the pipeline ───────────────────────────────────────────────────────
def _sweep_outcome_labels(store: MemoryStore) -> int:
    """Open one label review per run whose verdict the engine had to guess.

    This is the human gate as the *main* path: an opencode run reports tool errors
    and diffs but no verdict, so almost every automatic run lands here, and the
    queue is rebuilt from the observations rather than remembered in a counter —
    which makes the sweep idempotent and safe to re-run after a crash.
    """
    opened = 0
    for observation in store.list_loops_needing_review():
        loop_id = observation.get("loop_id") or ""
        if store.pending_review_id("", kind="outcome_label", loop_id=loop_id) is not None:
            continue
        signals = observation.get("signals") or {}
        store.add_review(
            memory_id="",
            loop_id=loop_id,
            kind="outcome_label",
            proposed_change={
                "kind": "label",
                "candidate_types": [],
                "reason": "the engine could not decide whether this run worked",
                "changes": {"outcome": signals.get("outcome_proposal", observation.get("outcome"))},
                "before": {},
            },
            evidence={
                "loop_id": loop_id,
                "task_id": observation.get("task_id") or "",
                "task": signals.get("task", ""),
                "cwd": signals.get("cwd", ""),
                "outcome": observation.get("outcome"),
                "quality_score": observation.get("quality_score"),
                "confidence": observation.get("confidence"),
                "mass": signals.get("mass"),
                "score": signals.get("score"),
                "present": signals.get("present", []),
                "absent": signals.get("absent", []),
                "reasons": signals.get("reasons", []),
                "signals": {k: v for k, v in signals.items()
                            if k not in ("present", "absent", "reasons")},
                "memories_used": memories_of_loop(store, loop_id),
            },
        )
        opened += 1
    return opened


def run_learning(*, store: Optional[MemoryStore] = None, apply: bool = True) -> dict[str, Any]:
    """Run one learning cycle over the store's candidates and observations."""
    owns_store = store is None
    store = store or MemoryStore()
    try:
        promotion = load_policy("promotion")
        rejection = load_policy("rejection")
        # Only unconsumed candidates. Re-reading the whole history each cycle is
        # what made an already-approved promotion open a fresh review forever.
        candidates = store.list_open_candidates()
        memories = {m["memory_id"]: m for m in store.memories_for_scoring()}

        linkage = store.linkage_by_memory()
        groups = group_candidates(candidates, linkage)
        # One pairwise scan per cycle, indexed by memory. Asking
        # ``conflicts_for(memory_id, all_memories)`` inside the loop re-scanned
        # every pair for every group, which is cubic in the size of the store.
        conflicts_by_id = conflict_mod.index_by_id(
            conflict_mod.find_conflicts(list(memories.values()))
        )
        results: list[dict[str, Any]] = []
        reviews_created = 0
        promoted: list[dict[str, Any]] = []
        max_promotions = int(promotion["max_promotions"])

        for memory_id in sorted(groups):
            group = groups[memory_id]
            candidate_ids = [c.get("candidate_id") for c in group["candidates"] if c.get("candidate_id")]
            memory = memories.get(memory_id)
            duplicate = None
            if memory is None:
                proposal = _proposal_of(group)
                if proposal is not None:
                    verdict = dedupe_mod.classify(store, proposal)
                    if verdict["action"] == "merge":
                        target = str(verdict["match"]["memory_id"])
                        existing = store.get_memory(target)
                        if existing is not None:
                            # One fact, one row: the arriving evidence joins the
                            # memory that already states it. Candidates stay
                            # `create`-typed, which keeps the human in the loop —
                            # a duplicate is not self-approving evidence.
                            memory_id = target
                            memory = existing
                            memories.setdefault(target, existing)
                            group["memory_id"] = target
                            group["executions"] |= {
                                run["loop_id"] for run in linkage.get(target, [])
                            }
                            group["source_hashes"] |= {
                                run["source_hash"]
                                for run in linkage.get(target, [])
                                if run.get("source_hash")
                            }
                            duplicate = verdict["match"]
                    elif verdict["action"] == "review":
                        review_id, created = _open_conflict_review(store, group, verdict, proposal)
                        if created:
                            reviews_created += 1
                        store.consume_candidates(candidate_ids, consumed_by=f"conflict:{review_id}")
                        results.append(
                            {
                                "memory_id": verdict["match"]["memory_id"],
                                "candidate_id": group["best_candidate_id"],
                                "candidate_types": sorted(
                                    c.get("candidate_type", "") for c in group["candidates"]
                                ),
                                "status": "review",
                                "validation_runs": len(group["executions"]),
                                "quality_score": group["best_quality"],
                                "confidence": 0.0,
                                "checks": {},
                                "rejection_reason": (
                                    f"possible duplicate of {verdict['match']['memory_id']} "
                                    f"(ratio {verdict['scores']['ratio']})"
                                ),
                                "evidence_sources": sorted(group["executions"]),
                                "memory_exists": True,
                                "proposal": proposal,
                                "conflicts": [],
                                "gate": "conflict",
                                "review_id": review_id,
                                "promotion": None,
                                "duplicate_of": verdict["match"],
                            }
                        )
                        continue
            result = validate_group(
                group, promotion=promotion, rejection=rejection, memory=memory
            )
            result["duplicate_of"] = duplicate
            result["conflicts"] = conflicts_by_id.get(memory_id, []) if memory else []
            result["gate"] = None
            result["review_id"] = None
            result["promotion"] = None
            consumed_by = "rejected"

            if result["status"] in ("validated", "hypothesis"):
                if _can_auto_promote(result, memory, result["conflicts"]) and len(promoted) < max_promotions:
                    result["gate"] = "auto"
                    if apply:
                        result["promotion"] = apply_promotion(result, store)
                        promoted.append(result["promotion"])
                        consumed_by = f"auto:{result['promotion'].get('status')}"
                    else:
                        consumed_by = "not_applied"
                else:
                    if len(promoted) >= max_promotions and _can_auto_promote(result, memory, result["conflicts"]):
                        # The cap is a throttle on one cycle, not a verdict on the
                        # memory: it becomes a review so the decision is still made.
                        result["rejection_reason"] = (
                            f"auto-promotion cap of {max_promotions} reached this cycle"
                        )
                    result["gate"] = "review"
                    review_id, created = _create_review(group, result, memory, store)
                    result["review_id"] = review_id
                    if created:
                        reviews_created += 1
                    consumed_by = f"review:{review_id}"
            elif result["status"] == "review":
                result["gate"] = "review"
                review_id, created = _create_review(group, result, memory, store)
                result["review_id"] = review_id
                if created:
                    reviews_created += 1
                consumed_by = f"review:{review_id}"
            else:
                store.add_event(
                    event_type="learning.rejected",
                    payload={"memory_id": memory_id, "reason": result["rejection_reason"]},
                )

            # Rejected groups are consumed too, or the next cycle recomputes the
            # same rejection for the same reason, forever.
            if apply:
                store.consume_candidates(candidate_ids, consumed_by=consumed_by)
            results.append(result)

        labels_queued = _sweep_outcome_labels(store) if apply else 0

        evaluations = evaluate_mod.summarize(evaluate_mod.evaluate_all(store))
        summary = {
            "candidates": len(candidates),
            "memory_groups": len(groups),
            "promoted": len(promoted),
            "reviews_created": reviews_created,
            "rejected": sum(1 for r in results if r["status"] == "rejected"),
            "outcome_labels_queued": labels_queued,
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
    """The queue, with each review's evidence counted as of now.

    The stored snapshot says how many runs supported the decision when it was
    opened. A reused review (the same proposal arriving from a later run) has more
    than that, and a reviewer deciding on "one run" who is actually looking at
    three is deciding on a number nobody wrote down on purpose.
    """
    owns_store = store is None
    store = store or MemoryStore()
    try:
        reviews = store.list_reviews(status=status)
        loops = store.evidence_loops_by_review()
        for review in reviews:
            gathered = loops.get(int(review["review_id"]), [])
            review["evidence_loops"] = gathered
            review["runs_now"] = len(gathered)
        return reviews
    finally:
        if owns_store:
            store.close()


def _resolve_conflict(store: MemoryStore, review: dict[str, Any]) -> dict[str, Any]:
    """Approving a conflict review: the newer statement replaces the one it supersedes.

    Neither side is deleted. The old row keeps its history and turns
    ``superseded``, which takes it out of recall, and the new row is born exactly
    where a human-approved proposal is born — ``active`` but with hypothesis-level
    evidence, because being preferred over a near-duplicate is not the same as
    being proven. Rejecting the review goes the other way and is handled by
    :func:`reject_review`, which needs no special case: nothing is written.
    """
    review_id = review["review_id"]
    change = dict(review.get("proposed_change") or {})
    if change.get("action") != "supersede":
        return {
            "review_id": review_id,
            "status": "malformed",
            "reason": "a conflict review must carry a supersede instruction",
        }
    new = dict(change.get("new") or {})
    if not new.get("title") or not new.get("body"):
        return {"review_id": review_id, "status": "rejected", "reason": "the proposed wording is gone"}
    old_id = str(change.get("supersedes") or review.get("memory_id") or "")
    old = store.get_memory(old_id)
    if old is None:
        return {
            "review_id": review_id,
            "status": "stale",
            "reason": "the memory this proposal would replace no longer exists",
        }

    scope = new.get("scope") or old.get("scope") or "global"
    if new.get("scope") not in (None, "", scope) and new.get("scope") != scope:
        return {
            "review_id": review_id,
            "status": "malformed",
            "reason": "a conflict may only be resolved inside one scope",
        }
    if dedupe_mod.key_for({**new, "scope": scope}) == old.get("dedupe_key"):
        # The same fact in other words is not a replacement; it is the same row.
        # Creating a second one would violate the very index that caught it.
        store.set_review_status(review_id, "approved")
        store.add_event(
            event_type="learning.conflict_resolved",
            payload={"review_id": review_id, "memory_id": old_id, "result": "no_new_row"},
        )
        return {
            "review_id": review_id,
            "status": "approved",
            "promotion": {
                "memory_id": old_id,
                "status": "no_new_row",
                "kind": "conflict",
                "reason": "same fact key as the existing memory",
            },
        }

    memory_id = str(new.get("memory_id") or "")
    if not memory_id:
        # Checked before anything is retired: the proposal reserved its id when it
        # was drafted, and without one there is nothing to write. Superseding the
        # old row first would leave the store with two losses instead of one fact.
        return {
            "review_id": review_id,
            "status": "malformed",
            "reason": "the proposal carries no reserved memory_id",
        }

    store.update_memory_fields(old_id, status="superseded")
    store.upsert_memory(
        {
            "memory_id": memory_id,
            "type": new.get("type") or "episodic",
            "category": new.get("category") or "",
            "title": new.get("title") or "",
            "body": new.get("body") or "",
            "scope": scope,
            "when_to_apply": new.get("when_to_apply") or "",
            "status": "active",
            "lane": "hypothesis",
            "evidence_level": "hypothesis",
            "confidence": "low",
            "supersedes": old_id,
            "version": int(old.get("version", 1) or 1) + 1,
            "source_task": new.get("task_id") or "",
            "source_session": new.get("session_id") or "",
            "source_project": new.get("cwd") or "",
            "source_loop_id": new.get("loop_id") or "",
        },
        tags=new.get("tags") or [],
        roles=new.get("roles") or [],
    )
    store.set_review_status(review_id, "approved")
    store.add_event(
        event_type="learning.conflict_resolved",
        payload={"review_id": review_id, "new": memory_id, "superseded": old_id},
    )
    return {
        "review_id": review_id,
        "status": "approved",
        "promotion": {
            "memory_id": memory_id,
            "status": "created",
            "kind": "conflict",
            "supersedes": old_id,
            "title": new.get("title"),
        },
    }


def approve_review(review_id: int, *, store: Optional[MemoryStore] = None) -> dict[str, Any]:
    """Approve a pending review and apply its effect to the store."""
    owns_store = store is None
    store = store or MemoryStore()
    try:
        review = store.get_review(review_id)
        if review is None:
            return {"review_id": review_id, "status": "not_found"}
        if review["status"] != "pending":
            return {"review_id": review_id, "status": "already_decided", "review_status": review["status"]}
        kind = review.get("kind", "promotion")
        if kind == "conflict":
            return _resolve_conflict(store, review)
        if kind != "promotion":
            # A label request is not answered by "yes": approving it would invent a
            # verdict, which is the thing the gate exists to avoid.
            return {
                "review_id": review_id,
                "status": "needs_label",
                "kind": kind,
                "hint": f"aos review label {review_id} --outcome success|partial|failure",
            }

        effect = dict(review.get("proposed_change") or {})
        # A create effect needs the words of the proposed memory, which live in
        # the evidence rather than the promise: the row does not exist yet, so
        # the proposal text is the only place they are written down.
        effect.setdefault("proposal", (review.get("evidence") or {}).get("proposal"))
        promotion = apply_effect(store, memory_id=review["memory_id"], effect=effect)
        if promotion["status"] == "stale":
            # The review is closed as `stale` rather than left pending: leaving it
            # open would block the pipeline from filing one that describes the
            # memory as it now is, and the queue would hold a request nobody can
            # ever answer correctly.
            store.set_review_status(review_id, "stale")
            store.add_event(
                event_type="learning.review_stale",
                payload={"review_id": review_id, "memory_id": review["memory_id"],
                         "drifted": promotion.get("drifted", {})},
            )
            return {"review_id": review_id, "status": "stale", "promotion": promotion}
        if promotion["status"] not in ("applied", "created", "recorded"):
            # Nothing was written and the review stays open: a missing payload is
            # a defect to fix, not a decision to record.
            return {"review_id": review_id, "status": promotion["status"], "promotion": promotion}
        store.set_review_status(review_id, "approved")
        store.add_event(
            event_type="learning.review_approved",
            payload={
                "review_id": review_id,
                "memory_id": review["memory_id"],
                "kind": promotion.get("kind"),
                "result": promotion.get("status"),
            },
        )
        return {"review_id": review_id, "status": "approved", "promotion": promotion}
    finally:
        if owns_store:
            store.close()


def reject_review(
    review_id: int, *, as_outcome: str = "", store: Optional[MemoryStore] = None
) -> dict[str, Any]:
    """Reject a pending review.

    The memory is left untouched, but the rejection is not inert: the candidates
    behind it are already consumed by the cycle that opened this review, so the
    same proposal does not come back every run; and ``as_outcome`` relabels the
    run the review was about, which is how "that was a failure" becomes a
    weakening signal instead of a shrug.
    """
    owns_store = store is None
    store = store or MemoryStore()
    try:
        review = store.get_review(review_id)
        if review is None:
            return {"review_id": review_id, "status": "not_found"}
        if review["status"] != "pending":
            return {"review_id": review_id, "status": "already_decided", "review_status": review["status"]}

        relabelled = None
        if as_outcome:
            if as_outcome not in OUTCOMES:
                return {"review_id": review_id, "status": "rejected", "error": f"unknown outcome: {as_outcome}"}
            relabelled = apply_verdict(
                store,
                loop_id=review.get("loop_id") or "",
                outcome=as_outcome,
                source=f"review:{review_id}",
            )
            if relabelled is None and review.get("kind") == "outcome_label":
                return {"review_id": review_id, "status": "not_found", "error": "loop observation is gone"}
        elif review.get("kind") == "outcome_label":
            # Nobody labelled the run. Take it out of the queue without inventing
            # a verdict: the observation stays as it was, marked as reviewed.
            store.clear_loop_review_flag(review.get("loop_id") or "")

        store.set_review_status(review_id, "rejected")
        store.add_event(
            event_type="learning.review_rejected",
            payload={
                "review_id": review_id,
                "memory_id": review["memory_id"],
                "loop_id": review.get("loop_id") or "",
                "as_outcome": as_outcome,
            },
        )
        return {
            "review_id": review_id,
            "status": "rejected",
            "memory_id": review["memory_id"],
            "relabelled": relabelled,
        }
    finally:
        if owns_store:
            store.close()


def label_review(
    review_id: int,
    outcome: str,
    *,
    quality_score: Optional[float] = None,
    store: Optional[MemoryStore] = None,
) -> dict[str, Any]:
    """Answer an outcome-label review: the human verdict becomes the run's record.

    This is the main path, not an escape hatch. An opencode run reports tool errors
    and diffs but no pass/fail, so almost every automatic loop arrives here with
    ``needs_review`` set and no candidates; whatever is decided here is what the
    learning pipeline gets to work with.
    """
    owns_store = store is None
    store = store or MemoryStore()
    try:
        if outcome not in OUTCOMES:
            return {"review_id": review_id, "status": "invalid", "error": f"unknown outcome: {outcome}"}
        review = store.get_review(review_id)
        if review is None:
            return {"review_id": review_id, "status": "not_found"}
        if review["status"] != "pending":
            return {"review_id": review_id, "status": "already_decided", "review_status": review["status"]}
        if review.get("kind") != "outcome_label":
            return {
                "review_id": review_id,
                "status": "wrong_kind",
                "kind": review.get("kind"),
                "error": "only outcome_label reviews can be labelled; approve or reject this one",
            }

        applied = apply_verdict(
            store,
            loop_id=review.get("loop_id") or "",
            outcome=outcome,
            quality_score=quality_score,
            source=f"review:{review_id}",
        )
        if applied is None:
            return {"review_id": review_id, "status": "not_found", "error": "loop observation is gone"}

        store.set_review_status(review_id, "approved", outcome=outcome)
        store.add_event(
            event_type="learning.run_labelled",
            payload={"review_id": review_id, "loop_id": review.get("loop_id"), "outcome": outcome},
        )
        return {
            "review_id": review_id,
            "status": "labelled",
            "outcome": outcome,
            "quality_score": applied["quality_score"],
            "candidates_created": applied["candidates_created"],
            "proposal_created": applied["proposal_created"],
            "observations_updated": applied["observations_updated"],
        }
    finally:
        if owns_store:
            store.close()


def apply_verdict(
    store: MemoryStore,
    *,
    loop_id: str,
    outcome: str,
    quality_score: Optional[float] = None,
    source: str = "",
) -> Optional[dict[str, Any]]:
    """Rewrite a run's observations with a human verdict, then propose what it implies.

    Returns the effect counts, or ``None`` when the loop has no observations left
    to relabel.
    """
    if not loop_id:
        return None
    rows = store.list_observations(loop_id=loop_id)
    if not rows:
        return None
    target = next((r for r in rows if not r.get("memory_id")), rows[0])

    rules = load_policy("outcome")
    quality = (
        float(quality_score)
        if quality_score is not None
        else float(rules[f"{outcome}_quality"])
    )
    updated = store.set_observation_outcome(
        int(target["observation_id"]),
        outcome=outcome,
        quality_score=quality,
        confidence=1.0,
        needs_review=False,
    )

    signals = target.get("signals") or {}
    memories = [m for m in (signals.get("memories_used") or memories_of_loop(store, loop_id)) if m]
    promotion = load_policy("promotion")
    created = 0
    candidate_type = candidate_type_for(outcome, quality, promotion=promotion)
    if candidate_type:
        created = add_candidates_for_memories(
            store,
            candidate_type=candidate_type,
            memories=memories,
            loop_id=loop_id,
            payload={
                "task_id": target.get("task_id") or "",
                "outcome": outcome,
                "quality_score": quality,
                "session_id": target.get("session_id") or "",
                "source_hash": target.get("source_hash") or "",
                "confidence": 1.0,
                "labelled_by": source,
            },
        )

    proposed = 0
    if should_propose(outcome=outcome, memories_used=memories, needs_review=False):
        proposal = proposal_for_loop(
            loop_id=loop_id,
            task_text=signals.get("task", ""),
            outcome=outcome,
            cwd=signals.get("cwd", ""),
            category=signals.get("category", ""),
            skills=signals.get("skills", []),
            files_changed=signals.get("files_changed", []),
            quality_score=quality,
        )
        store.add_candidate(
            candidate_type="create",
            target_memory=proposal["memory_id"],
            loop_id=loop_id,
            payload={
                **proposal,
                "task_id": target.get("task_id") or "",
                "session_id": target.get("session_id") or "",
                "source_hash": target.get("source_hash") or "",
                "proposed": True,
                "labelled_by": source,
            },
        )
        proposed = 1

    return {
        "quality_score": quality,
        "observations_updated": updated,
        "candidates_created": created,
        "proposal_created": proposed,
    }
