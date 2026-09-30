"""Learning pipeline and human review gate tests.

The core safety property under test: a hypothesis, or a memory that only has
weak evidence, is never promoted automatically — it becomes a *pending*
review and only an explicit ``approve`` writes to the memory.
"""

from __future__ import annotations

import json

import pytest

from aos.config import get_paths
from aos.core.memory import conflict as conflict_mod
from aos.core.memory import evaluate as evaluate_mod
from aos.core.memory import policy as policy_mod
from aos.core.memory.evolve import (
    apply_promotion,
    approve_review,
    group_candidates,
    list_reviews,
    reject_review,
    run_learning,
    validate_group,
)
from aos.core.memory.policy import load_policy
from aos.core.memory.store import MemoryStore


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


def _add(store, memory_id, *, evidence_level="benchmark_evaluated", mtype="procedural", tags=None, **overrides):
    memory = {
        "memory_id": memory_id,
        "type": overrides.pop("type", mtype),
        "category": overrides.pop("category", "optimization"),
        "title": overrides.pop("title", memory_id),
        "body": overrides.pop("body", ""),
        "evidence_level": evidence_level,
        "confidence": overrides.pop("confidence", "low"),
        **overrides,
    }
    return store.upsert_memory(memory, tags=tags or [])


def _observe(store, memory_id, loop_id, *, quality=4.0, source_hash=None, outcome="success"):
    return store.add_observation(
        loop_id=loop_id,
        memory_id=memory_id,
        outcome=outcome,
        quality_score=quality,
        source_hash=source_hash or f"hash-{loop_id}",
    )


def _candidate(store, memory_id, loop_id, *, ctype="reinforce", quality=4.0):
    return store.add_candidate(
        candidate_type=ctype,
        target_memory=memory_id,
        loop_id=loop_id,
        payload={"quality_score": quality, "outcome": "success"},
    )


# ── (a) hypotheses are held, never auto-promoted ───────────────────────
def test_hypothesis_only_creates_pending_review(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 0
    assert report["summary"]["reviews_created"] == 1
    reviews = list_reviews(store=store, status="pending")
    assert len(reviews) == 1
    assert reviews[0]["memory_id"] == "H-1"
    # The memory itself must be untouched until a human approves.
    assert store.get_memory("H-1")["evidence_level"] == "hypothesis"


def test_low_evidence_memory_is_held(store):
    # Not a hypothesis by id, but only benchmark evidence -> still gated.
    _add(store, "M-LOW", evidence_level="benchmark_evaluated")
    _observe(store, "M-LOW", "L1")
    _observe(store, "M-LOW", "L2")
    _candidate(store, "M-LOW", "L1")

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 0
    assert report["summary"]["reviews_created"] == 1
    assert store.get_memory("M-LOW")["evidence_level"] == "benchmark_evaluated"


# ── (b) approve is what writes the memory ──────────────────────────────
def test_approve_review_applies_promotion(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")
    run_learning(store=store)
    review = list_reviews(store=store, status="pending")[0]

    result = approve_review(review["review_id"], store=store)

    assert result["status"] == "approved"
    memory = store.get_memory("H-1")
    assert memory["evidence_level"] == "runtime_validated"
    # `validated` used to be written into a column whose documented vocabulary
    # said active|degraded|archived_candidate, so the store held a state nothing
    # else recognised. The lifecycle name for "strong evidence reached" is
    # `verified`, and reaching it also ends the hypothesis lane: a promoted
    # memory must stop being presented as a guess.
    assert memory["status"] == "verified"
    assert memory["lane"] == "standard"
    assert memory["last_verified_at"], "promotion is the event that renews verification"
    assert memory["observation_count"] == 1
    assert store.get_review(review["review_id"])["status"] == "approved"


def test_reject_review_leaves_memory_untouched(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")
    run_learning(store=store)
    review = list_reviews(store=store, status="pending")[0]

    result = reject_review(review["review_id"], store=store)

    assert result["status"] == "rejected"
    assert store.get_memory("H-1")["evidence_level"] == "hypothesis"
    assert list_reviews(store=store, status="pending") == []


def test_double_approve_is_rejected(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")
    run_learning(store=store)
    review = list_reviews(store=store, status="pending")[0]
    approve_review(review["review_id"], store=store)

    again = approve_review(review["review_id"], store=store)

    assert again["status"] == "already_decided"


# ── (c) thresholds really come from the policy file ────────────────────
def test_policy_threshold_is_read_from_file(store):
    _add(store, "M1", evidence_level="runtime_validated")
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1")

    # Default policy (min_observations = 2) would auto-promote this memory.
    baseline = run_learning(store=store)
    assert baseline["summary"]["promoted"] == 1

    # Raise the bar via a policy file: the same evidence no longer qualifies.
    _add(store, "M2", evidence_level="runtime_validated")
    _observe(store, "M2", "L3")
    _observe(store, "M2", "L4")
    _candidate(store, "M2", "L3")
    policies = get_paths().policies_dir
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "promotion.json").write_text(json.dumps({"min_observations": 5}), encoding="utf-8")
    policy_mod.reload()
    try:
        report = run_learning(store=store)
    finally:
        (policies / "promotion.json").unlink()

    m2 = [r for r in report["results"] if r["memory_id"] == "M2"][0]
    assert m2["status"] == "rejected"
    assert "5" in m2["rejection_reason"]
    assert store.get_memory("M2")["evidence_level"] == "runtime_validated"


# ── auto-promotion of clean, strong evidence ───────────────────────────
def test_strong_evidence_auto_promotes(store):
    _add(store, "M1", evidence_level="runtime_validated")
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1", quality=4.0)

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 1
    assert report["summary"]["reviews_created"] == 0
    memory = store.get_memory("M1")
    assert memory["evidence_level"] == "independent_validated"
    assert memory["confidence"] == "medium"


def test_insufficient_observations_is_rejected(store):
    _add(store, "M1", evidence_level="runtime_validated")
    _observe(store, "M1", "L1")  # only one loop
    _candidate(store, "M1", "L1")

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 0
    assert report["summary"]["reviews_created"] == 0
    assert report["summary"]["rejected"] == 1


def test_missing_evidence_hash_is_rejected(store):
    _add(store, "M1", evidence_level="runtime_validated")
    store.add_observation(loop_id="L1", memory_id="M1", outcome="success", quality_score=4.0)
    _candidate(store, "M1", "L1")

    result = run_learning(store=store)["results"][0]

    assert result["status"] == "rejected"
    assert "source_hash" in result["rejection_reason"]


def test_weaken_requires_review(store):
    _add(store, "M1", evidence_level="runtime_validated")
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1", ctype="weaken")

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 0
    assert report["summary"]["reviews_created"] == 1
    assert list_reviews(store=store, status="pending")[0]["memory_id"] == "M1"


def test_type_confusion_is_rejected(store):
    # reinforce (a normal-lane type) aimed at a hypothesis id.
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce")

    result = run_learning(store=store)["results"][0]

    assert result["status"] == "rejected"
    assert "type confusion" in result["rejection_reason"]


def test_conflict_routes_to_review_not_promotion(store):
    _add(store, "M1", evidence_level="runtime_validated", tags=["centralized"])
    _add(store, "M2", evidence_level="runtime_validated", tags=["distributed"])
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1")

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 0
    assert report["summary"]["reviews_created"] == 1
    review = list_reviews(store=store, status="pending")[0]
    assert review["memory_id"] == "M1"
    assert review["evidence"]["conflicts"]


def test_no_duplicate_pending_review(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")

    run_learning(store=store)
    second = run_learning(store=store)

    assert second["summary"]["reviews_created"] == 0
    assert len(list_reviews(store=store, status="pending")) == 1


# ── the evaluator is actually wired into the pipeline ──────────────────
def test_run_learning_reports_effectiveness(store):
    _add(store, "M1", evidence_level="runtime_validated")
    # Loop-level outcomes (what record_outcome writes for every loop) plus the
    # per-memory observations the learning pipeline reads.
    store.add_observation(loop_id="L1", memory_id=None, outcome="success", quality_score=4.5)
    store.add_observation(loop_id="L2", memory_id=None, outcome="success", quality_score=4.0)
    store.add_observation(loop_id="L9", memory_id=None, outcome="failure", quality_score=0.5)
    _observe(store, "M1", "L1", quality=4.5)
    _observe(store, "M1", "L2", quality=4.0)
    _candidate(store, "M1", "L1")

    report = run_learning(store=store)

    assert report["summary"]["evaluations"]["evaluated"] == 1
    assert report["summary"]["evaluations"]["effective"] == 1


def test_evaluate_memory_needs_a_comparison_group(store):
    _add(store, "M1")
    _observe(store, "M1", "L1")
    store.add_observation(loop_id="L1", memory_id=None, outcome="success", quality_score=4.0)

    assert evaluate_mod.evaluate_memory("M1", store) is None


def test_compute_quality_score_rewards_structure():
    rich = "# Title\n\n- point\n\n```py\nx=1\n```\n\n" + "使用 API 配置 步骤 建议 例如 优化 权衡 边界 " * 5
    assert evaluate_mod.compute_quality_score(rich) > evaluate_mod.compute_quality_score("ok")


# ── unit: grouping and validation ──────────────────────────────────────
def test_group_candidates_counts_independent_loops(store):
    _add(store, "M1")
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1")

    groups = group_candidates(store.list_candidates(), store.list_observations())

    assert set(groups["M1"]["executions"]) == {"L1", "L2"}


def test_validate_group_hypothesis_first_observation(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")
    group = group_candidates(store.list_candidates(), store.list_observations())["H-1"]

    result = validate_group(
        group,
        promotion=load_policy("promotion"),
        rejection=load_policy("rejection"),
        memory=store.get_memory("H-1"),
    )

    assert result["status"] == "hypothesis"


# ── unit: conflict detection ───────────────────────────────────────────
def test_conflict_detects_opposing_tags():
    a = {"memory_id": "A", "tags": ["centralized"]}
    b = {"memory_id": "B", "tags": ["distributed"]}
    assert conflict_mod.detect_conflicts(a, b)
    assert conflict_mod.has_conflict("A", [a, b])


def test_no_conflict_for_unrelated_memories():
    a = {"memory_id": "A", "tags": ["mysql"], "title": "index tuning"}
    b = {"memory_id": "B", "tags": ["css"], "title": "grid layout"}
    assert conflict_mod.detect_conflicts(a, b) == []


# ── unit: apply_promotion is a no-op for a missing memory ──────────────
def test_apply_promotion_missing_memory(store):
    result = apply_promotion({"memory_id": "NOPE", "validation_runs": 2}, store)
    assert result["status"] == "rejected"
