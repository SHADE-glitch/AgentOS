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
    """One earned verdict for a run this memory was recalled into.

    Two facts, written where each belongs: the memory was in the run
    (``retrieval_log``), and the run ended this way (a loop-level observation).
    This used to be one per-memory row, which let the gate read "it was there"
    as "it helped".
    """
    store.log_retrieval(
        memory_id=memory_id, score=0.5, rank=1, loop_id=loop_id, query_hash=f"Q-{loop_id}"
    )
    return store.add_observation(
        loop_id=loop_id,
        memory_id=None,
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
    # The gate writes the fields it decided about, and nothing else:
    # `observation_count` is a usage counter owned by the record path. Letting the
    # gate write it too made every review unapprovable (see
    # test_approval_is_refused_when_the_memory_moved_first).
    assert memory["observation_count"] == 0
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
    # The run is on record and the memory was in it, but the run carries no
    # evidence hash — so there is nothing a reviewer could go back and check.
    store.log_retrieval(memory_id="M1", score=0.5, rank=1, loop_id="L1", query_hash="Q-L1")
    store.add_observation(loop_id="L1", memory_id=None, outcome="success", quality_score=4.0)
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

    groups = group_candidates(store.list_candidates(), store.linkage_by_memory())

    assert set(groups["M1"]["executions"]) == {"L1", "L2"}


def test_validate_group_hypothesis_first_observation(store):
    _add(store, "H-1", mtype="semantic", lane="hypothesis", evidence_level="hypothesis")
    _observe(store, "H-1", "L1")
    _candidate(store, "H-1", "L1", ctype="reinforce_hypothesis")
    group = group_candidates(store.list_candidates(), store.linkage_by_memory())["H-1"]

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


# ── the effect of a decision, not merely that one was taken ────────────
# The gate used to be tested by "a review appeared". That assertion survived a
# gate which raised a memory's evidence level when the candidates were asking for
# it to be lowered, because nothing checked what approval *wrote*. These tests are
# the ones that would have caught it.
def _weakened(store, memory_id="M1", *, evidence_level="runtime_validated", confidence="medium", runs=2):
    _add(store, memory_id, evidence_level=evidence_level, confidence=confidence)
    for index in range(runs):
        loop = f"L{index + 1}"
        _observe(store, memory_id, loop, outcome="failure", quality=0.0)
        _candidate(store, memory_id, loop, ctype="weaken", quality=0.0)
    run_learning(store=store)
    return list_reviews(store=store, status="pending")[0]


def test_approving_a_weaken_review_lowers_the_memory(store):
    review = _weakened(store)

    result = approve_review(review["review_id"], store=store)

    memory = store.get_memory("M1")
    assert result["promotion"]["kind"] == "weaken"
    # Down the ladder. Before this, approving a weakening review moved the memory
    # *up*, which is the precise shape of "the store grows more confident while
    # getting worse".
    assert memory["evidence_level"] == "benchmark_evaluated"
    assert memory["confidence"] == "low"
    assert memory["decay_factor"] < 1.0
    assert memory["status"] != "verified"


def test_weakening_a_hypothesis_level_memory_retires_it(store):
    review = _weakened(store, evidence_level="hypothesis", confidence="low")

    approve_review(review["review_id"], store=store)

    memory = store.get_memory("M1")
    # There is no rung below hypothesis, so the second kind of consequence takes
    # over: the memory is deprecated rather than quietly kept at the floor.
    assert memory["evidence_level"] == "hypothesis"
    assert memory["status"] == "deprecated"


def test_weaken_penalty_is_bounded(store):
    review = _weakened(store, evidence_level="production_validated")
    approve_review(review["review_id"], store=store)
    first = store.get_memory("M1")["decay_factor"]
    for index in range(6):
        loop = f"W{index}"
        _observe(store, "M1", loop, outcome="failure", quality=0.0)
        _candidate(store, "M1", loop, ctype="weaken", quality=0.0)
        run_learning(store=store)
        pending = list_reviews(store=store, status="pending")
        if pending:
            approve_review(pending[0]["review_id"], store=store)

    assert store.get_memory("M1")["decay_factor"] >= 0.5 - 1e-9
    assert first <= 1.0


def test_mixed_evidence_is_never_applied_silently(store):
    _add(store, "M1", evidence_level="runtime_validated")
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1", ctype="reinforce")
    _candidate(store, "M1", "L2", ctype="weaken", quality=0.0)

    result = run_learning(store=store)["results"][0]

    assert result["status"] == "review"
    assert "both" in (result["rejection_reason"] or "").lower() or "human picks" in (
        result["rejection_reason"] or ""
    )
    review = list_reviews(store=store, status="pending")[0]
    assert review["proposed_change"]["kind"] == "mixed"

    approve_review(review["review_id"], store=store)

    # Approving a contradiction records the decision and moves no evidence: the
    # human said "keep it", not "it is proven".
    assert store.get_memory("M1")["evidence_level"] == "runtime_validated"


# ── proposals: a run asking for a new memory ──────────────────────────
def _proposal_candidate(store, **overrides):
    from aos.core.memory.record import proposal_for_loop

    payload = proposal_for_loop(
        loop_id="L1",
        task_text="fix the null pointer crash in the parser",
        outcome=overrides.pop("outcome", "failure"),
        cwd="/home/dev/repos/tracker",
        category="bugfix",
        skills=["bugfix"],
        files_changed=["src/parser.py"],
        quality_score=0.0,
    )
    payload.update(overrides)
    store.add_candidate(
        candidate_type="create",
        target_memory=payload["memory_id"],
        loop_id="L1",
        payload={**payload, "proposed": True, "source_hash": "hash-L1", "task_id": "T1"},
    )
    return payload


def test_a_proposal_becomes_a_review_never_an_auto_write(store):
    payload = _proposal_candidate(store)

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == 0, "a loop must not be able to write itself into memory"
    assert report["summary"]["reviews_created"] == 1
    assert store.get_memory(payload["memory_id"]) is None, "nothing exists until a human says so"


def test_approving_a_proposal_writes_what_the_review_showed(store):
    payload = _proposal_candidate(store)
    run_learning(store=store)
    review = list_reviews(store=store, status="pending")[0]
    assert review["proposed_change"]["kind"] == "create"
    assert review["evidence"]["proposal"]["title"] == payload["title"]

    result = approve_review(review["review_id"], store=store)

    memory = store.get_memory(payload["memory_id"])
    assert result["promotion"]["status"] == "created"
    assert memory["status"] == "active"
    assert memory["type"] == "failure"
    # Approval is about worth-remembering. The evidence for it is still one run,
    # so it stays in the hypothesis lane and is presented as a hint, not a rule.
    assert memory["evidence_level"] == "hypothesis"
    assert memory["lane"] == "hypothesis"
    assert memory["body"] == payload["body"]
    assert memory["scope"] == "project:tracker"
    assert memory["when_to_apply"]
    assert memory["source_loop_id"] == "L1"


def test_a_proposal_without_evidence_is_rejected(store):
    payload = _proposal_candidate(store)
    store.add_candidate(
        candidate_type="create",
        target_memory=payload["memory_id"],
        loop_id="",
        payload={**payload, "proposed": True},
    )
    store._conn.execute("DELETE FROM candidates WHERE loop_id = 'L1'")
    store._conn.commit()

    report = run_learning(store=store)

    assert report["summary"]["reviews_created"] == 0
    assert report["results"][0]["status"] == "rejected"


# ── the review is a promise the write must keep ───────────────────────
@pytest.mark.parametrize("kind", ["reinforce", "weaken"])
def test_what_a_review_promises_is_what_approval_does(store, kind):
    if kind == "reinforce":
        _add(store, "M1", evidence_level="benchmark_evaluated")
        _observe(store, "M1", "L1")
        _observe(store, "M1", "L2")
        _candidate(store, "M1", "L1")
        _candidate(store, "M1", "L2")
    else:
        _add(store, "M1", evidence_level="runtime_validated", confidence="medium")
        _observe(store, "M1", "L1", outcome="failure", quality=0.0)
        _observe(store, "M1", "L2", outcome="failure", quality=0.0)
        _candidate(store, "M1", "L1", ctype="weaken", quality=0.0)
        _candidate(store, "M1", "L2", ctype="weaken", quality=0.0)
    run_learning(store=store)
    review = list_reviews(store=store, status="pending")[0]
    promised = {k: v for k, v in review["proposed_change"]["changes"].items() if v != ""}

    approve_review(review["review_id"], store=store)

    memory = store.get_memory("M1")
    for key, value in promised.items():
        assert memory[key] == value, f"{key} was promised as {value!r}, written as {memory[key]!r}"


# ── candidates are spent, not re-litigated ────────────────────────────
def test_a_second_cycle_sees_no_candidates_at_all(store):
    # `benchmark_evaluated` is below the auto-trust bar, so this group lands on a
    # review rather than being applied silently.
    _add(store, "M1", evidence_level="benchmark_evaluated")
    _observe(store, "M1", "L1")
    _observe(store, "M1", "L2")
    _candidate(store, "M1", "L1")
    _candidate(store, "M1", "L2")
    first = run_learning(store=store)
    assert first["results"][0]["gate"] == "review"

    second = run_learning(store=store)

    assert second["summary"]["candidates"] == 0
    assert second["summary"]["memory_groups"] == 0
    assert store.list_candidates()[0]["consumed_by"] == f"review:{first['results'][0]['review_id']}"


def test_a_rejected_group_is_consumed_too(store):
    """The symptom, not the shape: a rejected candidate must not be re-rejected.

    Leaving rejected candidates open made every cycle recompute the same rejection
    for the same reason, and re-file the same review the pipeline had already
    answered — the reason `aos review list` used to grow without anything changing.
    """
    _add(store, "M2", evidence_level="runtime_validated")
    store.add_candidate(
        candidate_type="reinforce", target_memory="M2", loop_id="L9", payload={"quality_score": 4.0}
    )

    first = run_learning(store=store)

    assert first["results"][0]["status"] == "rejected"
    assert store.list_open_candidates() == [], "a cycle that looked at a candidate owns it"
    assert store.list_candidates()[-1]["consumed_by"] == "rejected"

    second = run_learning(store=store)

    assert second["summary"]["rejected"] == 0
    assert second["summary"]["reviews_created"] == 0


def test_the_auto_promotion_cap_throttles_instead_of_silencing(store):
    limit = int(load_policy("promotion")["max_promotions"])
    for index in range(limit + 2):
        memory_id = f"M{index}"
        _add(store, memory_id, evidence_level="production_validated")
        for loop in ("L1", "L2"):
            _observe(store, memory_id, loop)
        _candidate(store, memory_id, "L1")
        _candidate(store, memory_id, "L2")

    report = run_learning(store=store)

    assert report["summary"]["promoted"] == limit
    # The ones over the cap are not dropped: they become reviews, so a busy cycle
    # slows the gate down rather than losing the decision.
    assert report["summary"]["reviews_created"] == 2
    assert all(r["gate"] == "review" for r in report["results"] if r["promotion"] is None)


# ── an outcome review is answered by labelling, not by "yes" ──────────
def test_approving_an_outcome_review_is_refused(store):
    from aos.core.memory.evolve import _sweep_outcome_labels

    store.add_observation(
        loop_id="L1",
        memory_id=None,
        outcome="partial",
        quality_score=0.0,
        confidence=0.05,
        signals={"task": "fix the parser", "present": ["diff"], "absent": ["test_exit_code"]},
        needs_review=True,
        synthesised=True,
    )
    _sweep_outcome_labels(store)
    review = list_reviews(store=store, status="pending")[0]
    assert review["kind"] == "outcome_label"
    assert review["loop_id"] == "L1"

    result = approve_review(review["review_id"], store=store)

    assert result["status"] == "needs_label"
    assert "label" in result["hint"]
    assert store.get_review(review["review_id"])["status"] == "pending", "refusing must not decide it"


def test_the_label_sweep_is_idempotent(store):
    from aos.core.memory.evolve import _sweep_outcome_labels

    store.add_observation(
        loop_id="L1", memory_id=None, outcome="partial", needs_review=True, synthesised=True
    )
    assert _sweep_outcome_labels(store) == 1
    assert _sweep_outcome_labels(store) == 0
    assert len(list_reviews(store=store, status="pending")) == 1


def test_rejecting_a_label_without_a_verdict_still_clears_the_queue(store):
    from aos.core.memory.evolve import _sweep_outcome_labels

    store.add_observation(
        loop_id="L1", memory_id=None, outcome="partial", quality_score=0.0,
        needs_review=True, synthesised=True,
    )
    _sweep_outcome_labels(store)
    review = list_reviews(store=store, status="pending")[0]

    reject_review(review["review_id"], store=store)

    rows = store.list_observations(loop_id="L1")
    assert rows[0]["outcome"] == "partial", "no verdict was invented"
    assert store.list_loops_needing_review() == [], "and the same run is not asked twice"
    assert store.list_open_candidates() == []


def test_approval_is_refused_when_the_memory_moved_first(store):
    """A review approves the state it described, not whatever is in the row now.

    Found by running the gate for real: three failing runs piled up behind an
    open review, and approving it would have applied an effect computed against a
    two-run memory to a four-run one. The refusal is the correct answer, and the
    queue is supposed to be read soon — or re-run — rather than trusted to age
    well.
    """
    review = _weakened(store)
    store.update_memory_fields("M1", evidence_level="production_validated")

    result = approve_review(review["review_id"], store=store)

    assert result["status"] == "stale"
    assert result["promotion"]["drifted"]["evidence_level"] == {
        "was": "runtime_validated", "now": "production_validated"
    }
    assert store.get_memory("M1")["evidence_level"] == "production_validated", "nothing was written"
    assert store.get_review(review["review_id"])["status"] == "stale", "and the request is retired"
    assert store.list_open_candidates() == [], "the spent candidates stay spent"


def test_a_stale_approval_recovers_by_rerunning_learning(store):
    review = _weakened(store)
    store.update_memory_fields("M1", evidence_level="production_validated")
    approve_review(review["review_id"], store=store)
    _observe(store, "M1", "L3", outcome="failure", quality=0.0)
    _candidate(store, "M1", "L3", ctype="weaken", quality=0.0)

    run_learning(store=store)

    fresh = [r for r in list_reviews(store=store, status="pending") if r["memory_id"] == "M1"]
    assert len(fresh) == 1, "one review per memory, and it describes the memory as it is"
    assert fresh[0]["review_id"] != review["review_id"]
    assert fresh[0]["proposed_change"]["before"]["evidence_level"] == "production_validated"
    approve_review(fresh[0]["review_id"], store=store)
    assert store.get_memory("M1")["evidence_level"] == "real_project_validated"
