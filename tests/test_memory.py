"""Memory store, retrieval and recording tests."""

from __future__ import annotations

import json

import pytest

from aos.config import get_paths
from aos.core.memory import policy as policy_mod
from aos.core.memory.record import record_outcome
from aos.core.memory.retrieve import (
    compute_all_decay,
    compute_decay_factor,
    compute_static_relevance,
    retrieve,
)
from aos.core.memory.store import MemoryStore


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


def _add(store, memory_id, *, tags=None, roles=None, **overrides):
    memory = {
        "memory_id": memory_id,
        "type": overrides.pop("type", "procedural"),
        "category": overrides.pop("category", "optimization"),
        "title": overrides.pop("title", memory_id),
        "body": overrides.pop("body", ""),
        "evidence_level": overrides.pop("evidence_level", "benchmark_evaluated"),
        "confidence": overrides.pop("confidence", "high"),
        "observation_count": overrides.pop("observation_count", 5),
        # Recall only shows the gate its trustworthiest rows, and these fixtures
        # predate the status axis: they are about ranking, not about whether a
        # memory has been approved. A test that wants the filter itself says so.
        "status": overrides.pop("status", "active"),
        **overrides,
    }
    return store.upsert_memory(memory, tags=tags or [], roles=roles or [])


# ── store ──────────────────────────────────────────────────────────────
def test_upsert_and_get(store):
    mid = _add(store, "M1", tags=["mysql"], roles=["database-engineer"])
    got = store.get_memory(mid)
    assert got["memory_id"] == "M1"
    assert got["category"] == "optimization"
    assert store.count_memories() == 1


def test_upsert_is_idempotent(store):
    _add(store, "M1", tags=["mysql"])
    _add(store, "M1", tags=["mysql", "slow-query"], category="database")
    got = store.get_memory("M1")
    assert got["category"] == "database"
    assert sorted(store.memories_for_scoring()[0]["tags"]) == ["mysql", "slow-query"]
    assert store.count_memories() == 1


def test_delete_memory(store):
    _add(store, "M1")
    store.delete_memory("M1")
    assert store.get_memory("M1") is None


def test_auto_generated_id(store):
    mid = store.upsert_memory({"type": "episodic", "body": "x"})
    assert mid.startswith("M-")


# ── retrieval ──────────────────────────────────────────────────────────
QUERY = {
    "task_text": "Analyze MySQL slow query performance",
    "category": "optimization",
    "domains": ["database"],
    "roles": ["database-engineer"],
    "keywords": ["mysql", "slow-query"],
}


def test_retrieve_ranks_relevant_above_irrelevant(store):
    _add(store, "RELEVANT", tags=["mysql", "slow-query"], roles=["database-engineer"], category="optimization")
    _add(store, "IRRELEVANT", tags=["frontend", "css"], roles=["frontend-architect"], category="frontend")
    result = retrieve(QUERY, store=store)
    ids = [r["memory_id"] for r in result["results"]]
    assert ids[0] == "RELEVANT"
    assert "IRRELEVANT" not in ids


def test_retrieve_empty_store(store):
    result = retrieve(QUERY, store=store)
    assert result["results"] == []
    assert "error" in result


def test_retrieve_logs_history(store):
    _add(store, "M1", tags=["mysql", "slow-query"], roles=["database-engineer"])
    retrieve(QUERY, store=store, loop_id="L1")
    logged = store.list_retrievals(memory_id="M1")
    assert len(logged) == 1
    assert logged[0]["loop_id"] == "L1"
    assert logged[0]["rank"] == 1


def test_decay_factor_lowers_score(store):
    _add(store, "M1", tags=["mysql", "slow-query"], roles=["database-engineer"])
    base = retrieve(QUERY, store=store, log=False)["results"][0]["final_score"]
    store.set_decay_factor("M1", 0.5)
    decayed = retrieve(QUERY, store=store, log=False)["results"][0]["final_score"]
    assert decayed == pytest.approx(base * 0.5, abs=1e-3)
    assert decayed < base


def test_hypotheses_can_be_excluded(store):
    _add(store, "H1", type="semantic", lane="hypothesis", tags=["mysql", "slow-query"], roles=["database-engineer"])
    assert retrieve({**QUERY, "exclude_hypothesis": True}, store=store)["results"] == []
    included = retrieve(QUERY, store=store)["results"]
    assert included and included[0]["is_hypothesis"] is True
    assert included[0]["warning"]


def test_retrieval_policy_override(store):
    _add(store, "M1", tags=["mysql", "slow-query"], roles=["database-engineer"])
    policies = get_paths().policies_dir
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "retrieval.json").write_text(json.dumps({"min_score": 0.99}), encoding="utf-8")
    policy_mod.reload()
    try:
        assert retrieve(QUERY, store=store, log=False)["results"] == []
    finally:
        (policies / "retrieval.json").unlink()


# ── recall respects the lifecycle and the scope ────────────────────────
def test_recall_offers_only_statuses_the_gate_trusts(store):
    for status in ("candidate", "deprecated", "superseded", "invalidated", "archived"):
        _add(store, f"M-{status}", tags=["mysql", "slow-query"], status=status)
    _add(store, "M-active", tags=["mysql", "slow-query"], status="active")
    _add(store, "M-verified", tags=["mysql", "slow-query"], status="verified")

    ids = {r["memory_id"] for r in retrieve(QUERY, store=store, log=False)["results"]}

    assert ids == {"M-active", "M-verified"}


def test_a_demotion_changes_what_the_next_run_hears(store):
    """The screen this phase exists for: demoted means gone from the injection.

    Approving a weakening used to lower the evidence level and leave the memory
    recallable, so the negative half of learning was written down and never
    applied.
    """
    _add(store, "M1", tags=["mysql", "slow-query"], status="active")
    assert "M1" in {r["memory_id"] for r in retrieve(QUERY, store=store, log=False)["results"]}

    store.update_memory_fields("M1", status="deprecated")

    assert retrieve(QUERY, store=store, log=False)["results"] == []


def test_recall_does_not_borrow_another_projects_memory(store):
    _add(store, "M-ours", tags=["mysql", "slow-query"], scope="project:warehouse")
    _add(store, "M-theirs", tags=["mysql", "slow-query"], scope="project:billing")
    _add(store, "M-global", tags=["mysql", "slow-query"], scope="global")

    ids = {
        r["memory_id"]
        for r in retrieve(dict(QUERY, scope_project="warehouse"), store=store, log=False)["results"]
    }

    assert ids == {"M-ours", "M-global"}


def test_an_unknown_project_gets_global_memories_only(store):
    """Not knowing where we are is not a licence to use somebody else's facts."""
    _add(store, "M-scoped", tags=["mysql", "slow-query"], scope="project:warehouse")
    _add(store, "M-global", tags=["mysql", "slow-query"], scope="global")

    ids = {r["memory_id"] for r in retrieve(QUERY, store=store, log=False)["results"]}

    assert ids == {"M-global"}


def test_session_memory_is_only_offered_to_its_own_session(store):
    _add(store, "M-session", tags=["mysql", "slow-query"], scope="session:S1")

    assert retrieve(dict(QUERY, scope_session="S2"), store=store, log=False)["results"] == []
    ids = {r["memory_id"] for r in retrieve(dict(QUERY, scope_session="S1"), store=store, log=False)["results"]}
    assert ids == {"M-session"}


# ── expiry ─────────────────────────────────────────────────────────────
def test_expire_due_steps_one_level_per_pass(store):
    """Overdue retires by degrees: verified becomes active, active becomes deprecated.

    Nothing is deleted — the provenance stays history — but a fact about a version
    nobody re-checked stops being served as if it were current.
    """
    _add(store, "M-verified", tags=["mysql"], status="verified", revalidate_after="2026-01-01")
    _add(store, "M-active", tags=["mysql"], status="active", revalidate_after="2026-01-01")
    _add(store, "M-fresh", tags=["mysql"], status="active", revalidate_after="2099-01-01")

    moved = {m["memory_id"]: (m["from"], m["to"]) for m in store.expire_due(today="2026-09-30")}

    assert moved == {"M-verified": ("verified", "active"), "M-active": ("active", "deprecated")}
    assert store.get_memory("M-fresh")["status"] == "active"
    # Two passes take the ex-verified one all the way out of recall.
    store.expire_due(today="2026-09-30")
    assert store.get_memory("M-verified")["status"] == "deprecated"


def test_overdue_memory_is_labelled_when_it_is_still_recallable(store):
    from aos.core.memory import inject

    _add(
        store,
        "M1",
        tags=["mysql"],
        status="verified",
        revalidate_after="2026-01-01",
        body="use the pooled connection",
    )
    row = retrieve(dict(QUERY, scope_project=""), store=store, log=False)["results"][0]
    assert row["revalidate_after"] == "2026-01-01"

    rendered = inject.render([row], hypotheses=[], route=None, today="2026-09-30")

    line = next(line for line in rendered["text"].splitlines() if "可能已过期" in line)
    # The date a human must re-check is named, so "stale" is actionable rather
    # than a vibe.
    assert "2026-01-01" in line


# ── decay ──────────────────────────────────────────────────────────────
def test_compute_all_decay_penalises_unobserved_memory(store):
    _add(store, "M1", tags=["mysql"], observation_count=0)
    report = compute_all_decay(store)
    assert report["summary"]["total_memories"] == 1
    assert store.get_memory("M1")["decay_factor"] <= 0.85


def test_decay_pass_never_raises_a_penalty_the_gate_earned(store):
    """A weaken penalty is earned, and a recompute pass may not restore it.

    Measured on the development store: `aos memory refresh` moved a memory from
    0.512 (three approved weakens) back to 0.85, because the recency/usage writer
    assigned the column instead of combining with what was already in it. The
    column has two writers and only one of them is allowed to make a memory
    look better — the gate.
    """
    _add(store, "M1", tags=["mysql"], observation_count=0)
    store.set_decay_factor("M1", 0.512)

    compute_all_decay(store)

    assert store.get_memory("M1")["decay_factor"] == 0.512


def test_decay_pass_still_lowers_and_reports_what_it_persisted(store):
    """Taking the lower of the two must not turn into "keep whatever was there"."""
    _add(store, "M1", tags=["mysql"], observation_count=0, confidence="low")
    store.set_decay_factor("M1", 1.0)

    report = compute_all_decay(store)

    persisted = store.get_memory("M1")["decay_factor"]
    assert persisted < 1.0
    assert report["memories"][0]["decay_factor"] == persisted, (
        "the reported factor must be the one a reader will find in the store"
    )


def test_the_hypothesis_protection_window_uses_the_one_predicate_the_project_has():
    """A human-approved `failure` memory is in the hypothesis lane, and must age out like one.

    The project states "this row is a hypothesis" in `lane`/`evidence_level` — that is what
    `store.hypothesis_lane` reads and what the injector reads to mark a row "未验证，仅作提示".
    The decay pass was the one place still reading the `type` column, so a memory the human gate
    created from a failed run (`type='failure'`, `lane='hypothesis'`) kept its protection window
    forever: measured on the real store, `M-7B113D99` was injected into the next run and would be
    injected into every later one, with nothing ageing it. Two predicates for one concept is how
    a rule ends up honoured in one file and missed in another.
    """
    policy = policy_mod.load_policy("decay")
    past_window = "2020-01-01T00:00:00+00:00"  # far beyond hypothesis_max_days

    stub = {
        "memory_id": "M-STUB", "type": "failure", "lane": "hypothesis",
        "evidence_level": "hypothesis", "created_at": past_window, "observation_count": 1,
    }
    reasons = compute_decay_factor(stub, {}, 0.0, policy)["reasons"]
    assert "hypothesis: past protection window" in reasons, (
        "a hypothesis-lane row past its window must be decayed, whatever its type says"
    )

    # The same predicate the injector uses, not a blanket rule for every old memory.
    standard = {
        "memory_id": "M-REAL", "type": "failure", "lane": "standard",
        "evidence_level": "runtime_validated", "created_at": past_window, "observation_count": 1,
    }
    assert "hypothesis: past protection window" not in compute_decay_factor(standard, {}, 0.0, policy)["reasons"]


# ── recording ──────────────────────────────────────────────────────────
def _link(store, loop_id, memory_id, rank=1):
    """Record that a memory was in a run's context (linkage, nothing more)."""
    store.log_retrieval(memory_id=memory_id, score=0.5, rank=rank, loop_id=loop_id, query_hash="Q")


def test_record_outcome_writes_one_observation_per_run(store):
    """The run is the unit of evidence; the memories in it are not separate runs.

    Per-memory rows used to be written for everything recalled, then averaged
    back into each memory's own success rate — so being recalled raised a
    memory's rank, which raised how often it was recalled (R-006).
    """
    _add(store, "M1", tags=["mysql"])
    _link(store, "L1", "M1")
    counts = record_outcome(loop_id="L1", outcome="success", quality_score=1.0, memories_used=["M1"], store=store)
    assert counts["observations_recorded"] == 1
    rows = store.list_observations()
    assert [r["memory_id"] for r in rows] == [None]
    assert store.get_memory("M1")["observation_count"] == 1


def test_record_failure_creates_candidate_only_for_the_skill_that_was_used(store):
    _add(store, "M1", tags=["mysql"])
    _link(store, "L1", "M1")
    counts = record_outcome(
        loop_id="L1", outcome="failure", quality_score=0.0,
        memories_used=["M1"], skill_used="mysql", store=store,
    )
    assert counts["candidates_created"] == 1
    candidate = store.list_candidates()[0]
    assert candidate["candidate_type"] == "weaken"
    assert candidate["target_memory"] == "M1"
    assert "mysql" in candidate["payload_json"]


def test_record_high_quality_success_creates_candidate(store):
    _add(store, "M1", tags=["mysql"])
    _link(store, "L1", "M1")
    counts = record_outcome(
        loop_id="L1", outcome="success", quality_score=4.0,
        memories_used=["M1"], skill_used="mysql", store=store,
    )
    assert counts["candidates_created"] == 1
    assert store.list_candidates()[0]["candidate_type"] == "reinforce"


def test_being_recalled_alone_credits_nothing(store):
    """No host-reported skill ⇒ no attribution ⇒ no candidate, in either direction.

    A failure does not blame a memory that merely shared the prompt with it, and
    a success does not promote one. The human label path is what names memories.
    """
    _add(store, "M1", tags=["mysql"])
    _link(store, "L1", "M1")
    counts = record_outcome(
        loop_id="L1", outcome="failure", quality_score=0.0, memories_used=["M1"], store=store
    )
    assert counts["candidates_created"] == 0
    assert store.list_candidates() == []


def test_usage_stats_separates_linkage_from_verdicts(store):
    """``usage_count`` is where a memory has been; ``success_rate`` is what happened."""
    _add(store, "M1", tags=["mysql"])
    _link(store, "L1", "M1")
    _link(store, "L2", "M1")
    record_outcome(loop_id="L1", outcome="success", memories_used=["M1"], store=store)
    record_outcome(loop_id="L2", outcome="failure", memories_used=["M1"], store=store)

    stats = store.usage_stats()["M1"]
    assert stats["usage_count"] == 2          # linkage: two runs held it
    assert stats["outcome_count"] == 2        # verdicts: both were earned
    assert stats["successful_uses"] == 1
    assert stats["success_rate"] == 0.5


def test_unlabelled_run_is_neither_credit_nor_blame(store):
    """needs_review runs are excluded from the rate, so a guess cannot rank memories."""
    _add(store, "M1", tags=["mysql"])
    _link(store, "L1", "M1")
    record_outcome(loop_id="L1", outcome="success", memories_used=["M1"], needs_review=True, store=store)

    stats = store.usage_stats()["M1"]
    assert stats["usage_count"] == 1
    assert stats["outcome_count"] == 0
    assert stats["success_rate"] == 0.5       # no evidence, so no penalty either


def test_upsert_keeps_the_tags_that_came_inside_the_row(store):
    """A complete row handed over wholesale must not quietly lose its tags.

    `authoring.new_memory` returns a row that already carries `tags`, while
    `upsert_memory` used to write them only when they were also passed as a
    keyword — so a caller that did the obvious thing stored a memory the recall
    path can no longer find by its largest scoring term.
    """
    from aos.core.memory.authoring import new_memory

    store.upsert_memory(
        new_memory(
            title="改 Lua 脚本后先跑 eval 兼容性",
            body="两类改动分开提交。",
            type="procedural",
            tags=["lua", "redis"],
        )
    )

    row = store.memories_for_scoring()[0]
    assert sorted(row["tags"]) == ["lua", "redis"]


def test_a_two_character_chinese_tag_counts_as_a_task_match():
    """`len(tag) >= 3` is a Latin assumption that falls straight through to Chinese.

    缓存 / 配置 / 排序 are ordinary two-character Chinese words; `id` and `to` are not
    words worth matching on. Scoring the first like the second is one reason a purely
    Chinese task recalls nothing (defect V) — and no amount of hand-tagging fixes it
    while this rule treats character count as wordhood.
    """
    from aos.core.memory.retrieve import compute_static_relevance

    cjk = compute_static_relevance(
        {"category": "", "tags": ["缓存"], "roles": []},
        {"task_text": "清一下缓存的问题", "keywords": [], "domains": [], "roles": []},
    )
    latin = compute_static_relevance(
        {"category": "", "tags": ["id"], "roles": []},
        {"task_text": "fix the id collision", "keywords": [], "domains": [], "roles": []},
    )

    assert cjk > 0, "a two-character Chinese tag is a real match"
    assert latin == 0, "a two-letter Latin token is still noise"


# ── 阈值该判在 decay 之前还是之后（缺陷 AA / 裁决 ②′）──────────────────
def _two_tag_hit_row(store, s):
    """A memory whose only claim on this task is two matching Chinese tags."""
    from aos.core.memory.retrieve import retrieve

    return retrieve(
        {"task_text": "渲染层能不能自己调整召回排序", "category": "", "domains": [],
         "roles": [], "keywords": [], "scope_project": ""},
        store=s,
        log=False,
    )["results"]


def test_decay_orders_a_memory_but_does_not_ban_it_from_recall(store):
    """`decay_factor` at the policy's own floor used to retire a memory in silence.

    0.85 multiplying a 0.16 relevance gives 0.136, which is below min_score — so a
    weakened memory stops being recalled while its status stays `active` and nothing in
    `doctor` or the queue says so. `evolve.py`'s comment says decay should make a memory
    quieter, not kill it by arithmetic; the threshold is therefore judged on the
    pre-decay score, and decay keeps its ordering role.
    """
    from aos.core.memory.retrieve import retrieve

    _add(store, "M-WEAK", tags=["渲染层", "召回排序"], confidence="medium",
         evidence_level="runtime_validated", observation_count=3)
    _add(store, "M-STRONG", tags=["渲染层", "召回排序", "输出顺序"], confidence="high",
         evidence_level="runtime_validated", observation_count=3)
    store.set_decay_factor("M-WEAK", 0.5)

    results = retrieve(
        {"task_text": "渲染层能不能自己调整召回排序，看输出顺序", "category": "", "domains": [],
         "roles": [], "keywords": [], "scope_project": ""},
        store=store,
        log=False,
    )["results"]
    by_id = {r["memory_id"]: r for r in results}

    assert "M-WEAK" in by_id, "a memory at the decay floor is still recalled, just quieter"
    weak, strong = by_id["M-WEAK"], by_id.get("M-STRONG")
    assert weak["final_score"] < 0.15 <= weak["adaptive_score"], (
        "the gate looks at the pre-decay score; that is the whole fix"
    )
    assert strong is None or strong["final_score"] > weak["final_score"], (
        "decay still decides who is shown first"
    )
    assert [r["memory_id"] for r in results].index("M-WEAK") >= (
        0 if strong is None else [r["memory_id"] for r in results].index("M-STRONG")
    ), "the decayed memory cannot outrank the fresh one"


def test_a_single_tag_coincidence_is_still_not_a_recall(store):
    """The precision half of the same decision, measured rather than assumed.

    Moving the threshold ahead of decay must not turn "the task happened to use one of
    my tags" into a reason to inject a memory: one hit is 0.08 static, and no quality
    bonus (capped at +30%) lifts that over 0.15.
    """
    from aos.core.memory.retrieve import retrieve

    _add(store, "M-ONE", tags=["缓存键", "配置文件"], confidence="high",
         evidence_level="runtime_validated", observation_count=5)

    results = retrieve(
        {"task_text": "这个缓存键的命名风格不好", "category": "", "domains": [],
         "roles": [], "keywords": [], "scope_project": ""},
        store=store,
        log=False,
    )["results"]

    assert results == [], "one matching tag is a coincidence, not relevance"


def test_re_seeding_a_memory_cannot_undo_a_demotion(store):
    """`--force` is an author's tool; standing belongs to the gate.

    Measured before the fix: re-seeding raised a memory the gate had demoted from
    `benchmark_evaluated/low` back to whatever the seed file declares
    (`real_project_validated/high`) — a re-run of somebody's JSON overruled a human
    decision recorded in the store. Counters were already protected by this rule
    ("earned, not declared"); the fields that say how much to trust a memory were not.
    """
    from aos.core.memory.authoring import new_memory

    first = new_memory(
        title="插件只能 export default { id, server }",
        body="加载器会把每个导出当工厂调用。",
        category="config",
        evidence_level="runtime_validated",
        verified=True,
    )
    memory_id = store.upsert_memory(first, tags=["opencode", "plugin"])
    store.update_memory_fields(memory_id, evidence_level="benchmark_evaluated", confidence="low")

    rewritten = new_memory(
        title="插件只能 export default { id, server }（改过措辞）",
        body="加载器会把每个函数导出当工厂调用，整个插件会静默不加载。",
        category="config",
        evidence_level="runtime_validated",
        verified=True,
    )
    store.upsert_memory({**rewritten, "memory_id": memory_id}, tags=["opencode", "plugin", "loader"])

    after = store.get_memory(memory_id)
    assert after["title"].endswith("（改过措辞）"), "the author's rewrite of what it says still lands"
    assert after["evidence_level"] == "benchmark_evaluated", "a re-seed cannot un-demote"
    assert after["confidence"] == "low", "nor restore confidence the human lowered"
    row = next(m for m in store.memories_for_scoring() if m["memory_id"] == memory_id)
    assert sorted(row["tags"]) == ["loader", "opencode", "plugin"], "tags are content: those follow the author"


def test_the_author_path_cannot_touch_a_single_gate_column(store):
    """One list decides it: whatever the gate may write, a re-seed may not.

    Not a comment promising it — every column in `update_memory_fields`'s whitelist is
    set through the gate, then the memory is upserted again with none of them present.
    If the author path could write any one of them, this fails. That is what keeps the
    two lists from drifting apart later: adding a standing column to the gate without
    protecting it from `upsert_memory` breaks here rather than in somebody's store.
    """
    from aos.core.memory.authoring import new_memory
    from aos.core.memory.store import MemoryStore

    memory_id = store.upsert_memory(
        new_memory(title="原正文", body="原内容。", category="config", verified=True),
        tags=["old"],
    )
    standing = {
        "evidence_level": "runtime_validated",
        "confidence": "high",
        "status": "verified",
        "lane": "standard",
        "observation_count": 7,
        "decay_factor": 0.62,
        "last_verified_at": "2026-01-02T00:00:00+00:00",
        "supersedes": "M-GONE",
        "use_count": 3,
        "success_count": 2,
        "last_used_at": "2026-01-03T00:00:00+00:00",
    }
    assert sorted(standing) == sorted(MemoryStore._PROMOTABLE_FIELDS), (
        "the whitelist grew; this test has to cover the new column too"
    )
    store.update_memory_fields(memory_id, **standing)

    store.upsert_memory(
        {**new_memory(title="改过的正文", body="重新写过内容。", category="config", verified=True),
         "memory_id": memory_id},
        tags=["new"],
    )

    after = store.get_memory(memory_id)
    assert after["title"] == "改过的正文", "content still follows the author"
    assert sorted(store.memories_for_scoring()[0]["tags"]) == ["new"]
    moved = {key: (value, after[key]) for key, value in standing.items() if after[key] != value}
    assert not moved, f"the author path wrote gate columns: {moved}"


def test_the_earned_list_is_derived_from_the_gate_whitelist():
    """The exclusion is computed from `update_memory_fields`'s list, not retyped.

    A second literal list would be correct today and wrong the first time someone adds
    a column to one of them — the exact failure shape this repository keeps recording
    (declared in one place, honoured in another).
    """
    from aos.core.memory import store as store_module
    from pathlib import Path

    source = Path(store_module.__file__).read_text(encoding="utf-8")
    line = next(line for line in source.splitlines() if "earned =" in line)
    assert "_PROMOTABLE_FIELDS" in line, f"earned is hardcoded again: {line.strip()}"


# ── the fallback bucket and the gate's arithmetic (defect AH) ─────────
def test_the_routers_confession_of_ignorance_is_not_a_subject(store):
    """`fallback` means "I could not classify this" — two of those must not add up to a match.

    Measured live (round 14, defect AH): a human-approved lesson about checking a directory before
    naming a config file was injected into "写一首关于秋天的短诗", because the only thing the two tasks
    shared was the router's failure bucket — `category=fallback` on both sides, worth 0.15, and 0.15
    is exactly `min_score`. A bucket that fires precisely when nothing is known cannot be evidence of
    relevance, and it self-selects the unclassifiable — where a memory should be least trusted.
    """
    _add(store, "M-FALLBACK", category="fallback", tags=["fallback", "bugfix", "retry"],
         status="active", lane="standard", observation_count=0)

    unrelated = {"task_text": "帮我写一首关于秋天的短诗，四行就行", "category": "fallback",
                 "domains": [], "roles": ["code-reviewer"], "keywords": [], "scope_project": "test"}
    assert retrieve(unrelated, store=store, log=False)["results"] == [], (
        "a router that gave up on both sides must not produce a match"
    )

    # The subject still works when it is actually in the words: two real tag hits, no fallback.
    subject = {"task_text": "the glob and bugfix retry path is slow", "category": "",
               "domains": [], "roles": [], "keywords": [], "scope_project": ""}
    ids = [m["memory_id"] for m in retrieve(subject, store=store, log=False)["results"]]
    assert "M-FALLBACK" in ids, "content overlap must still be able to reach the gate"


def test_a_single_tag_hit_reveals_how_high_the_gate_actually_is(store):
    """The arithmetic behind defect V, stated where it cannot be missed — both entrances to the gate.

    There are two independent ways to reach `min_score = 0.15`, and they behave differently:

    - **The route names the subject.** `category_match` alone is worth 0.15, so a correctly routed
      task recalls the memory with *zero* content overlap — measured on the real store, a Chinese
      sentence sharing no tag with `M-SEED-PHASE010` scored exactly 0.15 and arrived.
    - **The task text contains the tags.** One literal hit is `0.20 * 0.40 = 0.08` (~0.086 with the
      best quality bonus a fresh memory can hold); two are 0.16 (~0.172). So one tag is not enough.

    AH removed the bucket that used to fake the first entrance, which leaves content as the only
    route for unclassifiable tasks — and there the bar is two literal tag hits, in either language.
    Language never mattered to the engine; overlap did. Moving the threshold is the owner's call
    (defect V); this pins the numbers so nobody has to infer them from a failure.
    """
    _add(store, "M-ONE", tags=["zephyr"], status="active", lane="standard", observation_count=0)
    _add(store, "M-TWO", tags=["zephyr", "quux"], status="active", lane="standard", observation_count=0)
    q = {"task_text": "the zephyr quux handler", "category": "", "domains": [], "roles": [],
         "keywords": [], "scope_project": ""}
    # The scoring view, not `get_memory`: tags live in a join table and only
    # `memories_for_scoring` assembles them, which is what the scorer is given in production.
    rows = {m["memory_id"]: m for m in store.memories_for_scoring()}
    one = compute_static_relevance(rows["M-ONE"], q)
    two = compute_static_relevance(rows["M-TWO"], q)
    assert one == pytest.approx(0.08) and two == pytest.approx(0.16)
    assert one * 1.075 < 0.15 <= two * 1.075, "one tag is not findable; two are"

    # The other entrance, pinned so the sentence above cannot be read as "tags are always required":
    # a route that names the category carries the memory with no overlap in the task text at all.
    routed = compute_static_relevance(
        rows["M-ONE"], {"task_text": "完全无关的一句话", "category": "", "domains": [],
                        "roles": [], "keywords": [], "scope_project": ""}
    )
    assert routed == 0.0, "no route and no overlap is no match — that is what AH closed"
    named = _add(store, "M-ROUTE", category="performance", status="active", lane="standard",
                 observation_count=0)
    rows = {m["memory_id"]: m for m in store.memories_for_scoring()}
    assert compute_static_relevance(rows["M-ROUTE"], {
        "task_text": "完全无关的一句话", "category": "performance", "domains": [],
        "roles": [], "keywords": [], "scope_project": ""}
    ) == pytest.approx(0.15), "a named category alone reaches the gate, with zero content overlap"


# ── proposal drafting (defect AG) ──────────────────────────────────────
_LONG_TASK = (
    "给配置文件加缓存时缓存键该怎么取才不会撞，另外阶段汇报里的回滚成本要不要单独写一句，"
    "还有如果同一份配置被两个项目各自解析一遍会不会出现两种键，还有测试里要不要专门造一个碰撞的用例，"
    "以及文档里是不是该把这条写进维护手册的常见坑一节里，顺手也看看 CI 的缓存目录"
)


def _draft(**extra):
    from aos.core.memory.record import proposal_for_loop

    kwargs = {
        "loop_id": "LOOP-AG-1",
        "task_text": _LONG_TASK,
        "outcome": "failure",
        "cwd": "/home/dev/repos/warehouse",
        "category": "bugfix",
        "skills": ["bugfix"],
        "files_changed": ["app/cache.py", "app/config.py"],
    }
    kwargs.update(extra)
    return proposal_for_loop(**kwargs)


def test_a_proposal_states_what_is_provable_and_names_the_hole_it_cannot_fill():
    """The draft is a factual record, so it must say what it knows and mark what it cannot know.

    Measured on the real store: the memory the human gate approved read
    `任务「<the question, echoed>」的结果：failure。 路由：report。 位置：…`, `when_to_apply` was cut
    mid-token by `task[:40]`, and `inject` renders `type='failure'` behind `不要：` — so a prompt was
    told "不要：<an incident line>" while the promise this layer makes
    (`docs/decision/positioning.md:240`) is "不要…**因为**…". The engine summarises with no model, and
    no signal states *why* a run failed: distilling the signals that do exist is the honest half, and
    the other half is labelling the hole instead of hiding it behind an echo of the question.
    """
    draft = _draft(signals={"tool_errors": 2, "test_exit_code": 1, "session_error": True})

    assert "改动 2 个文件" in draft["body"], draft["body"]
    assert "工具错误 2" in draft["body"]
    assert "测试退出码 1" in draft["body"]
    assert "session_error" in draft["body"], "a hard failure is a fact worth carrying"
    assert "未归因" in draft["body"], "the cause no signal shows must be marked, not papered over"
    assert "结果：failure。" not in draft["body"], "the body is no longer a template repeating the title"

    assert draft["when_to_apply"].endswith("时"), draft["when_to_apply"]
    assert "warehouse" in draft["when_to_apply"], "the project it happened in is part of when it applies"
    assert draft["title"].endswith("…"), "a cut title must look cut, not read as a finished claim"
    assert len(draft["body"]) <= 500


def test_a_draft_with_no_signals_invents_nothing_and_still_marks_the_hole():
    """Absence is stated as absence: no tool errors observed is not "no tool errors happened"."""
    draft = _draft(files_changed=[], signals={})

    assert "改动" not in draft["body"], draft["body"]
    assert "工具错误" not in draft["body"]
    assert "未归因" in draft["body"]
    assert "缺证" in draft["body"], "the reviewer must see that the run reported nothing to distil"


def test_the_same_episode_drafts_the_same_thing_twice():
    """Identity is derived from the draft, so drafting must be deterministic or dedupe breaks."""
    a = _draft(signals={"tool_errors": 1})
    b = _draft(signals={"tool_errors": 1})
    assert a["memory_id"] == b["memory_id"] and a["body"] == b["body"]


def test_a_proposal_quotes_the_model_and_keeps_it_at_a_distance():
    """The answer a run gave is material for the reviewer, not a fact the draft asserts.

    `response_summary` is weighted 0.00 in the verdict for a documented reason (`policy.py`:
    reading the model's own prose for "done" is what made every delegated run score identically).
    Defect AG's `因为` needs something to react to, and the answer is the only text a run produces —
    so it is quoted, attributed, capped, and marked unverified. It never enters `可证`, and the hole
    stays open beside it, because a quote is not a cause.
    """
    draft = _draft(signals={"response_summary": "我会改用 p95 作为唯一首指标，均值放在附注里。"})

    assert "模型自述（未核实）" in draft["body"], draft["body"]
    assert "p95" in draft["body"]
    assert "可证：模型自述" not in draft["body"], "a quote is not evidence"
    assert "未归因" in draft["body"], "quoting the answer must not close the hole"
    assert "缺证" not in draft["body"] or "response_summary" not in draft["body"].split("缺证")[1], (
        "a signal that arrived is not listed as unreported"
    )


def test_an_empty_answer_is_not_reported_as_a_missing_one():
    """Absence has two shapes: the host sent nothing, or it sent nothing useful."""
    assert "模型自述" not in _draft(signals={"response_summary": ""})["body"]
    assert "模型自述" not in _draft(signals={})["body"]


def test_a_crowded_draft_drops_the_gaps_before_the_quote():
    """When the budget bites, the least load-bearing clause goes first — and the hole never does."""
    draft = _draft(
        files_changed=[f"src/module_{i}/deeply/nested/path_{i}.py" for i in range(8)],
        signals={
            "tool_errors": 3, "test_exit_code": 1, "build_exit_code": 0, "validation_status": "FAILED",
            "response_summary": "把键换成解析后的绝对路径，因为两个项目会各自解析同一份配置。",
        },
    )

    assert len(draft["body"]) <= 500
    assert "模型自述（未核实）" in draft["body"], "the material a reviewer needs outranks the gap list"
    assert "缺证" not in draft["body"]
    assert "未归因" in draft["body"]


def test_a_crowded_draft_keeps_the_hole_and_drops_the_least_that_matters():
    """The budget may not eat the one clause that tells a human something is missing.

    The draft ends by naming what it cannot know, and the body is capped — so a long file list and a
    full set of signals would slice off exactly the part that makes the row reviewable. When the
    budget bites, the droppable clause is the 缺证 list; the hole is not.
    """
    draft = _draft(
        files_changed=[f"src/module_{i}/deeply/nested/path_{i}.py" for i in range(8)],
        signals={
            "tool_errors": 3, "test_exit_code": 1, "build_exit_code": 0,
            "validation_status": "FAILED", "todos_unfinished": 2, "session_error": True,
        },
    )

    assert len(draft["body"]) <= 500, len(draft["body"])
    assert draft["body"].rstrip().endswith("。"), draft["body"][-80:]
    assert "未归因" in draft["body"], "the hole must survive the cap"


# ── the trajectory of a run (defect AJ) ────────────────────────────────
_SWITCH = [
    {"n": 1, "tool": "bash", "method": "pytest", "exit": 1, "ok": False},
    {"n": 2, "tool": "bash", "method": "python -m pytest", "exit": 0, "ok": True},
]
_PLAIN = [
    {"n": 1, "tool": "bash", "method": "pytest", "exit": 0, "ok": True},
]


def test_a_trajectory_is_written_as_a_process_and_not_as_a_provable_fact():
    """「试了 A，A 不行，改用 B，成了」is the lesson — and it is a *process*, not evidence.

    Listing the attempts under 可证 would let the draft assert that the run went well because the
    steps are numbered, when a numbered list of failures says nothing about the verdict. So the
    trajectory gets its own clause, and the type follows it: a run that ended well *after* failing
    is a practice to reuse (`做法`), not an incident to avoid and not a bare episode.
    """
    draft = _draft(outcome="success", quality_score=3.5, signals={"tool_trace": _SWITCH, "tool_calls": 2})

    assert "过程：#1 pytest 失败 → #2 python -m pytest 通过" in draft["body"], draft["body"]
    assert "可证" not in draft["body"].split("过程")[0], "the attempts must not join the provable facts"
    assert draft["type"] == "procedural", draft["type"]
    assert draft["outcome"] == "success"


def test_a_run_with_no_trajectory_says_nothing_about_a_process():
    """Nothing observed is not a process of one step, and a clean run is not a practice."""
    empty = _draft(outcome="success", quality_score=3.5, signals={"tool_trace": [], "tool_calls": 0})
    assert "过程" not in empty["body"], empty["body"]
    assert empty["type"] == "episodic"

    clean = _draft(outcome="success", quality_score=3.5, signals={"tool_trace": _PLAIN, "tool_calls": 1})
    assert "过程" not in clean["body"], "one successful attempt is not a change of method"
    assert clean["type"] == "episodic"


def test_the_identity_of_a_lesson_ignores_the_trajectory_that_proved_it():
    """The account of *how* it went is not part of *what* was learned.

    The memory id is derived from the fact key, and the fact key hashes the body. A trajectory in
    the body therefore splits one lesson into one row per retelling — the same task failing in a
    different order would open a second review and, after approval, a second row stating one fact.
    So the identity is computed from the draft without its 过程 clause, while the body the human
    reads keeps it.
    """
    first = _draft(outcome="success", quality_score=3.5, signals={"tool_trace": _SWITCH, "tool_calls": 2})
    second = _draft(
        outcome="success", quality_score=3.5,
        signals={"tool_trace": [
            {"n": 1, "tool": "bash", "method": "pytest", "exit": 1, "ok": False},
            {"n": 2, "tool": "bash", "method": "pytest", "exit": 1, "ok": False},
            {"n": 3, "tool": "bash", "method": "python -m pytest", "exit": 0, "ok": True},
        ], "tool_calls": 3},
    )

    assert first["body"] != second["body"], "the two accounts do differ"
    assert first["memory_id"] == second["memory_id"], (
        "and one lesson must still be one memory, not one per retelling"
    )
    assert first.get("dedupe_key"), "the row needs an explicit key, or upsert re-derives it from the body"


def test_the_last_step_is_the_one_the_budget_cannot_drop():
    """A truncated trajectory that loses its ending is worse than no trajectory.

    The body is capped at 500 and the injected line at 280 characters; the clause that says what
    finally worked sits at the end of the list, which is exactly where a cap bites first. So the
    attempts are thinned from the middle and the last step is kept whole — the same rule the
    plugin applies to the list it sends.
    """
    long_trace = [{"n": i, "tool": "bash", "method": f"tool{i}", "exit": 1, "ok": False} for i in range(1, 15)]
    long_trace.append({"n": 15, "tool": "bash", "method": "python -m pytest", "exit": 0, "ok": True})
    draft = _draft(
        outcome="success", quality_score=3.5,
        files_changed=[f"src/module_{i}/deeply/nested/path_{i}.py" for i in range(8)],
        signals={"tool_trace": long_trace, "tool_calls": 15, "response_summary": "改用 python -m pytest 就好了。"},
    )

    assert len(draft["body"]) <= 500, len(draft["body"])
    assert "#15 python -m pytest 通过" in draft["body"], draft["body"]
    assert "#1 tool1 失败" in draft["body"], "and the beginning of the account survives too"
    assert "未归因" in draft["body"], "the hole is still the last thing standing"


def test_a_malformed_trajectory_degrades_to_no_account_rather_than_an_invented_one(store):
    """A host that sends garbage about its steps must not produce a story.

    The trace crosses a contract boundary as JSON a third party assembles; entries arrive as
    strings, nulls or dicts without the agreed keys. Skipping what is not a step is the difference
    between a missing account and a fabricated one — and the second is what this layer is not
    allowed to write into a memory.
    """
    from aos.core.memory.record import describe_trace, proposal_for_loop

    for garbage in ([], ["pytest failed"], [None, {"exit": "not-a-number"}], None, {"n": 1}):
        draft = proposal_for_loop(
            loop_id="L-BAD", task_text="修复构建", outcome="success", quality_score=3.5,
            category="infra", signals={"tool_trace": garbage},
        )
        assert "过程" not in draft["body"], repr(garbage)
        assert draft["type"] == "episodic", repr(garbage)
    assert describe_trace({"tool_trace": [{"n": 1, "tool": "bash", "exit": 1, "ok": False}]}) == (
        "过程：#1 bash 失败"
    ), "a step without a method is still a step, and stays honest about not naming one"
