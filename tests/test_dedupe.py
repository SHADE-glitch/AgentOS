"""Proposal identity and duplicate resolution (P3).

Three defects live here. ``dedupe_key`` was a column nobody filled, so the unique
index that was built to stop duplicates could never fire; a proposal minted a new
random id every time, so the same task failing three times became three separate
questions; and "similar but not certain" had nowhere to go, so it was either
silently merged or silently duplicated.
"""

from __future__ import annotations

import sqlite3

import pytest

from aos.core.learning import dedupe as dedupe_mod
from aos.core.learning import identity
from aos.core.memory import conflict as conflict_mod
from aos.core.memory import evolve
from aos.core.memory.record import proposal_for_loop, record_outcome
from aos.core.memory.store import MemoryStore


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


def _proposal_row(title="修复 cache key 碰撞导致命中率下降", body="任务「修复 cache key 碰撞」的结果：failure。", **extra):
    return proposal_for_loop(
        loop_id=extra.pop("loop_id", "L1"),
        task_text=extra.pop("task_text", title),
        outcome=extra.pop("outcome", "failure"),
        cwd=extra.pop("cwd", "/home/dev/repos/warehouse"),
        category=extra.pop("category", "bugfix"),
        skills=extra.pop("skills", ["bugfix"]),
        **extra,
    )


def _seed(store, *, memory_id, title, body, scope="project:warehouse", tags=None, status="active", **extra):
    store.upsert_memory(
        {
            "memory_id": memory_id,
            "type": extra.pop("type", "failure"),
            "category": extra.pop("category", "bugfix"),
            "title": title,
            "body": body,
            "status": status,
            "scope": scope,
            "evidence_level": extra.pop("evidence_level", "runtime_validated"),
            "confidence": "high",
            "when_to_apply": "改动缓存 key 之前",
            **extra,
        },
        tags=tags or ["cache", "key"],
    )


# ── layer 1: the fact key ──────────────────────────────────────────────
def test_fact_key_folds_spelling_but_not_synonyms():
    key = lambda title, body="x": identity.fact_key(
        title=title, body=body, category="build", mtype="semantic", scope="project:a"
    )

    assert key("Java 17") == key("java17") == key("JAVA  17,")
    assert key("Java 17") != key("jdk 17"), "a lexical key may not pretend to know synonyms"
    assert key("Java 17") != key("Java 18")


def test_every_writer_gets_a_dedupe_key(store):
    """The index was built in v2 and never fired, because nothing filled the column."""
    store.upsert_memory({"memory_id": "M1", "type": "semantic", "title": "Java 17", "body": "use LTS"})

    assert store.get_memory("M1")["dedupe_key"]


def test_the_same_fact_cannot_be_stored_twice_in_one_scope(store):
    _seed(store, memory_id="M-A", title="未归一化的输入不要直接拼 cache key", body="会碰撞。")

    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_memory(
            {
                "memory_id": "M-B",
                "type": "failure",
                "category": "bugfix",
                "title": "未归一化的输入不要直接拼 cache key",
                "body": "会碰撞。",
                "scope": "project:warehouse",
            }
        )


def test_the_same_fact_in_another_scope_is_a_different_fact(store):
    _seed(store, memory_id="M-A", title="未归一化的输入不要直接拼 cache key", body="会碰撞。")
    store.upsert_memory(
        {
            "memory_id": "M-B",
            "type": "failure",
            "category": "bugfix",
            "title": "未归一化的输入不要直接拼 cache key",
            "body": "会碰撞。",
            "scope": "project:billing",
        }
    )

    assert {m["memory_id"] for m in store.list_memories()} == {"M-A", "M-B"}


# ── layer 2/3: similarity and the grey band ────────────────────────────
def test_near_duplicate_wording_classifies_as_merge(store):
    _seed(
        store,
        memory_id="M-A",
        title="未归一化的输入不要直接拼 cache key，会引发键碰撞",
        body="曾回滚两天。",
    )

    verdict = dedupe_mod.classify(
        store,
        {
            "memory_id": "M-NEW",
            "type": "failure",
            "category": "bugfix",
            "title": "未归一化的输入不要直接拼 cache key，会引发键碰撞",
            "body": "曾回滚两天! 缓存键必须归一化。",
            "scope": "project:warehouse",
            "tags": ["cache", "key"],
        },
    )

    assert verdict["action"] == "merge"
    assert verdict["match"]["memory_id"] == "M-A"
    assert verdict["scores"]["ratio"] >= dedupe_mod.MERGE_AT


def test_half_rewritten_fact_goes_to_a_human_not_to_either(store):
    """The grey band is a question, not an action: neither merge nor invent.

    Ratio measured on this pair is 0.677 with identical tags — the wording is
    close enough that one of the two is probably wrong, and far enough that code
    must not choose.
    """
    _seed(
        store,
        memory_id="M-A",
        title="未归一化的输入不要直接拼 cache key，会引发键碰撞",
        body="曾回滚两天。",
    )

    verdict = dedupe_mod.classify(
        store,
        {
            "memory_id": "M-NEW",
            "type": "failure",
            "category": "bugfix",
            "title": "cache key 需要归一化，否则会引发键碰撞",
            "body": "曾回滚两天。",
            "scope": "project:warehouse",
            "tags": ["cache", "key"],
        },
    )

    assert dedupe_mod.GREY_AT <= verdict["scores"]["ratio"] < dedupe_mod.MERGE_AT
    assert verdict["scores"]["tag_jaccard"] == 1.0, "tags agree, and still do not decide"
    assert verdict["action"] == "review"


def test_a_different_fact_is_left_alone(store):
    _seed(store, memory_id="M-A", title="未归一化的输入不要直接拼 cache key", body="会碰撞。")

    verdict = dedupe_mod.classify(
        store,
        {
            "memory_id": "M-NEW",
            "type": "procedural",
            "category": "test",
            "title": "改完 Redis Lua 脚本先跑 eval 兼容性再跑过期回归",
            "body": "两类改动分开提交。",
            "scope": "project:warehouse",
            "tags": ["redis"],
        },
    )

    assert verdict["action"] == "new"


def test_retired_memories_do_not_compete_for_the_same_fact(store):
    _seed(
        store,
        memory_id="M-A",
        title="未归一化的输入不要直接拼 cache key",
        body="会碰撞。",
        status="superseded",
    )

    ids = [m["memory_id"] for m in dedupe_mod.compares_to(store, {"memory_id": "M-NEW", "scope": "project:warehouse"})]

    assert ids == []


# ── proposal identity through the loop ─────────────────────────────────
def test_the_same_episode_gets_the_same_id_whatever_the_loop_is():
    first = _proposal_row(loop_id="L1")
    second = _proposal_row(loop_id="L2")

    assert first["memory_id"] == second["memory_id"]
    # The key itself is filled by the store on write, so every writer gets it
    # whether or not it remembered to ask for one.
    assert "dedupe_key" not in first


def test_three_failures_of_one_task_leave_one_review_not_three(store):
    """The queue used to grow a new decision per run; accumulation is the fix.

    With random ids each arrival was its own group of one run, which failed the
    two-independent-runs requirement and was thrown away as `rejected` — so the
    store lost three fragments of the same lesson and a human saw none of them.
    """
    for loop_id in ("L1", "L2", "L3"):
        proposal = _proposal_row(loop_id=loop_id)
        record_outcome(
            loop_id=loop_id,
            outcome="failure",
            quality_score=0.0,
            memories_used=[],
            needs_review=False,
            source_hash=f"hash-{loop_id}",
            proposal=proposal,
            store=store,
        )

    report = evolve.run_learning(store=store)
    pending = evolve.list_reviews(store=store, status="pending")

    assert len({c["target_memory"] for c in store.list_candidates()}) == 1
    assert report["summary"]["memory_groups"] == 1
    assert len(pending) == 1
    assert pending[0]["kind"] == "promotion"


def test_approving_the_stable_proposal_writes_exactly_one_memory(store):
    for loop_id in ("L1", "L2"):
        record_outcome(
            loop_id=loop_id,
            outcome="failure",
            quality_score=0.0,
            memories_used=[],
            needs_review=False,
            source_hash=f"hash-{loop_id}",
            proposal=_proposal_row(loop_id=loop_id),
            store=store,
        )
    evolve.run_learning(store=store)
    review = evolve.list_reviews(store=store, status="pending")[0]

    evolve.approve_review(review["review_id"], store=store)

    rows = store.list_memories()
    assert len(rows) == 1
    assert rows[0]["status"] == "active"


def test_a_duplicate_proposal_becomes_evidence_for_the_row_that_exists(store):
    task = "修复 cache key 碰撞导致命中率下降"
    _seed(
        store,
        memory_id="M-A",
        title=task,
        body=f"任务「{task}」的结果：failure。",
        category="bugfix",
    )
    proposal = _proposal_row(title=task, task_text=task)
    record_outcome(
        loop_id="L1",
        outcome="failure",
        quality_score=0.0,
        memories_used=[],
        needs_review=False,
        source_hash="hash-L1",
        proposal=proposal,
        store=store,
    )

    report = evolve.run_learning(store=store)

    group = report["results"][0]
    assert group["duplicate_of"]["memory_id"] == "M-A"
    assert group["memory_id"] == "M-A", "the arriving evidence is filed against the existing row"
    assert len(store.list_memories()) == 1, "no second row for one fact"


def test_grey_band_opens_a_conflict_review_and_approving_supersedes(store):
    _seed(
        store,
        memory_id="M-A",
        title="未归一化的输入不要直接拼 cache key，会引发键碰撞",
        body="曾回滚两天。",
    )
    proposal = {
        "memory_id": "M-NEW1",
        "type": "failure",
        "category": "bugfix",
        "title": "cache key 需要归一化，否则会引发键碰撞",
        "body": "曾回滚两天。",
        "scope": "project:warehouse",
        "tags": ["cache", "key"],
        "when_to_apply": "新增缓存 key 时",
        "loop_id": "L1",
        "cwd": "/home/dev/repos/warehouse",
    }
    record_outcome(
        loop_id="L1",
        outcome="failure",
        quality_score=0.0,
        memories_used=[],
        needs_review=False,
        source_hash="hash-L1",
        proposal=proposal,
        store=store,
    )

    evolve.run_learning(store=store)
    conflicts = [r for r in evolve.list_reviews(store=store, status="pending") if r["kind"] == "conflict"]
    assert len(conflicts) == 1
    assert len(store.list_memories()) == 1, "the grey band writes nothing by itself"

    result = evolve.approve_review(conflicts[0]["review_id"], store=store)

    assert result["status"] == "approved"
    assert store.get_memory("M-A")["status"] == "superseded"
    created = store.get_memory("M-NEW1")
    assert created["supersedes"] == "M-A"
    assert created["status"] == "active"
    assert created["version"] == 2


def test_rejecting_a_conflict_keeps_the_existing_memory(store):
    _seed(
        store,
        memory_id="M-A",
        title="未归一化的输入不要直接拼 cache key，会引发键碰撞",
        body="曾回滚两天。",
    )
    evolve._open_conflict_review(
        store,
        {"executions": {"L1"}, "best_candidate_id": None, "candidates": [{"loop_id": "L1"}]},
        {
            "match": {
                "memory_id": "M-A",
                "title": "existing",
                "status": "active",
                "ratio": 0.71,
                "tag_jaccard": 0.2,
            }
        },
        {
            "memory_id": "M-NEW2",
            "type": "failure",
            "title": "similar wording",
            "body": "similar claim",
            "scope": "project:warehouse",
        },
    )
    review = [r for r in evolve.list_reviews(store=store, status="pending") if r["kind"] == "conflict"][0]

    evolve.reject_review(review["review_id"], store=store)

    assert store.get_memory("M-A")["status"] == "active"
    assert store.get_memory("M-NEW2") is None


def test_conflicts_are_scanned_once_per_cycle_with_the_same_results(store):
    """The index is a performance fix, so it has to be shown to agree with the scan."""
    _seed(store, memory_id="M-A", title="use a synchronous gateway", body="centralized", tags=["synchronous", "monolith"])
    _seed(store, memory_id="M-B", title="use an async gateway", body="distributed", tags=["async", "microservice"])
    rows = store.memories_for_scoring()

    indexed = conflict_mod.index_by_id(conflict_mod.find_conflicts(rows))
    per_id = {
        row["memory_id"]: conflict_mod.conflicts_for(row["memory_id"], rows) for row in rows
    }

    assert set(indexed) == set(per_id)
    for memory_id, pairs in per_id.items():
        assert sorted(p["memory_a"] + p["memory_b"] for p in pairs) == sorted(
            p["memory_a"] + p["memory_b"] for p in indexed[memory_id]
        )
