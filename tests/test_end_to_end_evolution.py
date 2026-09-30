"""One failure changing what happens next — the loop, end to end.

This file is the existence proof for everything Phase 3 wired up: a real task goes
through ``preflight``, comes back through ``postflight`` without a verdict, is
labelled by a human, becomes a memory through the review gate, and is then *found
again* by the next task's recall. Every other test in the suite checks a part; this
one checks that the parts are connected, which is the property the store's tables
growing for fifty tasks conspicuously did not demonstrate.

It drives the lifecycle functions rather than a subprocess because the assertion
that matters is about state, not about a pipe — the CLI boundary has its own file.
"""

from __future__ import annotations

import pytest

from aos.core.loop import lifecycle
from aos.core.memory import evolve
from aos.core.memory.store import MemoryStore


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


def _post(doc: dict, **payload) -> dict:
    return lifecycle.postflight(
        task_id=doc["task_id"], loop_id=doc["loop_id"], session_id=doc.get("session_id", ""), **payload
    )


def test_a_failure_becomes_a_warning_the_next_run_hears(store):
    """spec §二十二 D: 一次失败如何改变下一次行为."""
    first = lifecycle.preflight(task="修复 Redis Lua 脚本里 key 过期时间算错的问题", task_id="T1")

    # Nothing in the store yet, so there is nothing to say.
    assert first["memory"]["injection"]["text"] == ""

    result = _post(first, cwd="/home/dev/repos/tracker")
    assert result["final_status"] == "partial"
    assert result["learning"]["needs_review"] is True

    # An unlabelled run proposed nothing: the engine does not turn its own
    # uncertainty into a change to long-term memory.
    assert result["learning"]["candidates_recorded"] == 0
    assert store.list_open_candidates() == []

    pending = evolve.list_reviews(store=store, status="pending")
    labels = [r for r in pending if r["kind"] == "outcome_label"]
    assert len(labels) == 1, "the run that could not be judged is the queue's first item"
    assert labels[0]["loop_id"] == first["loop_id"]
    assert labels[0]["evidence"]["task"].startswith("修复 Redis Lua")

    labelled = evolve.label_review(labels[0]["review_id"], "failure", store=store)
    # The review's own state, not a verb for this call: `review list` shows the
    # same word, so a caller comparing the two is not translating.
    assert labelled["status"] == "approved"
    assert labelled["outcome"] == "failure"
    assert labelled["proposal_created"] == 1, "a failed task with no memory recalled must be remembered"

    # Labelling settles the cycle it just fed: the person who answered the queue
    # sees the consequence in the same command, instead of waiting for some later
    # run to sweep the candidate up.
    assert labelled["learning"]["reviews_created"] == 1
    review = evolve.list_reviews(store=store, status="pending")[0]
    assert review["kind"] == "promotion"
    assert review["proposed_change"]["kind"] == "create"
    assert review["evidence"]["proposal"]["type"] == "failure"

    approved = evolve.approve_review(review["review_id"], store=store)
    assert approved["promotion"]["status"] == "created"
    memory_id = approved["promotion"]["memory_id"]

    second = lifecycle.preflight(task="再改一次 Lua 脚本的 key 过期时间", task_id="T2")

    text = second["memory"]["injection"]["text"]
    assert "<agent_os>" in text and "</agent_os>" in text
    assert memory_id in second["memory"]["injection"]["memory_ids"]
    # The shape a failure memory takes is a warning, not a suggestion, and the
    # trigger clause says when it applies — the two things that make a remembered
    # failure actionable rather than merely present.
    assert "不要" in text
    assert "适用：" in text
    assert second["memory"]["retrieved"] >= 1


def test_the_same_run_is_not_asked_for_a_label_twice(store):
    first = lifecycle.preflight(task="给 parser 加上空指针检查", task_id="T1")
    _post(first, cwd="/home/dev/repos/tracker")

    # postflight's own evolve stage filed it, so the queue already has exactly one.
    assert len(evolve.list_reviews(store=store, status="pending")) == 1

    second = evolve.run_learning(store=store)

    assert second["summary"]["outcome_labels_queued"] == 0
    assert len(evolve.list_reviews(store=store, status="pending")) == 1


def test_a_labelled_success_recalls_and_reinforces_the_memory_it_used(store):
    from aos.core.memory.authoring import new_memory

    store.upsert_memory(
        new_memory(
            title="改 Lua 脚本后先跑 eval 兼容性再跑过期回归",
            body="两类改动分开提交，各跑一次测试。",
            type="procedural",
            category="bugfix",
            tags=["lua", "redis"],
            scope="project:tracker",
            when_to_apply="修改 Redis Lua 脚本之后",
            evidence_level="runtime_validated",
            verified=True,
        )
    )
    memory_id = store.list_memories()[0]["memory_id"]

    for index in range(2):
        # cwd travels with the request, because the memory this run should hear
        # is scoped to that repository — an unscoped recall would silently drop it.
        doc = lifecycle.preflight(
            task="调整 Redis Lua 脚本的过期逻辑", task_id=f"T{index}", cwd="/home/dev/repos/tracker"
        )
        assert memory_id in [m["memory_id"] for m in doc["memory"]["memories"]], "recalled"
        # The host says which skill it actually used. Without that report a
        # success credits nothing: the memory was merely in the room (R-006).
        result = _post(
            doc,
            cwd="/home/dev/repos/tracker",
            outcome="success",
            quality_score=4.5,
            signals={"skill_used": "lua"},
        )
        assert result["final_status"] == "completed"
        assert result["learning"]["needs_review"] is False
        assert result["learning"]["candidates_recorded"] == 1

    evolve.run_learning(store=store)

    memory = store.get_memory(memory_id)
    assert memory["evidence_level"] == "independent_validated", "two clean runs lifted it one rung"
    assert memory["observation_count"] == 2


def test_an_approved_weakening_takes_the_memory_out_of_the_next_prompt(store):
    """Negative learning, end to end: a failure the human agreed with must sting.

    This is the loop's other half, and the one the store used to fake. A
    hypothesis-lane memory is recalled, a run it was part of fails with the host
    reporting that skill, the gate refuses to act on weakening evidence without a
    person, the person approves — and only then does the next task stop hearing
    it. Nothing here deletes the memory: its provenance is history, its status is
    retired, and recall is what honours that.
    """
    from aos.core.memory.authoring import new_memory

    store.upsert_memory(
        new_memory(
            title="未归一化的输入不要直接拼进 cache key",
            body="同项目里引发过键碰撞，回滚耗时两天。",
            type="failure",
            category="bugfix",
            tags=["cache", "key"],
            scope="project:warehouse",
            when_to_apply="改动缓存 key 的拼接逻辑之前",
        )
    )
    row = store.list_memories()[0]
    memory_id = row["memory_id"]
    store.update_memory_fields(memory_id, status="active")

    def recalled(doc):
        block = doc["memory"]["injection"]
        return memory_id in block["memory_ids"] or memory_id in [
            m["memory_id"] for m in block["structured"]
        ]

    first = lifecycle.preflight(
        task="修复 cache key 碰撞导致的命中率下降", task_id="N1", cwd="/home/dev/repos/warehouse"
    )
    assert recalled(first), "the memory is offered before anyone disagrees with it"

    result = _post(
        first,
        cwd="/home/dev/repos/warehouse",
        outcome="failure",
        quality_score=0.0,
        signals={"skill_used": "cache"},
    )
    assert result["learning"]["needs_review"] is False
    assert result["learning"]["candidates_recorded"] == 1

    run = evolve.run_learning(store=store)
    assert run["summary"]["promoted"] == 0, "weakening evidence never applies itself"
    pending = evolve.list_reviews(store=store, status="pending")
    weakening = [r for r in pending if r["memory_id"] == memory_id]
    assert len(weakening) == 1
    # A failed run also proposes a memory of its own, so the queue holds two
    # rows here. That pile-up on repeat failures is what P3's stable proposal
    # identity is for; it is not this test's subject.
    assert len(pending) == 2

    evolve.approve_review(weakening[0]["review_id"], store=store)

    assert store.get_memory(memory_id)["status"] == "deprecated"
    second = lifecycle.preflight(
        task="修复 cache key 碰撞导致的命中率下降", task_id="N2", cwd="/home/dev/repos/warehouse"
    )
    assert not recalled(second), "a retired memory must not come back into the prompt"
