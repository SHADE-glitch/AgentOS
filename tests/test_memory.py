"""Memory store, retrieval and recording tests."""

from __future__ import annotations

import json

import pytest

from aos.config import get_paths
from aos.core.memory import policy as policy_mod
from aos.core.memory.record import record_outcome
from aos.core.memory.retrieve import compute_all_decay, retrieve
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


# ── decay ──────────────────────────────────────────────────────────────
def test_compute_all_decay_penalises_unobserved_memory(store):
    _add(store, "M1", tags=["mysql"], observation_count=0)
    report = compute_all_decay(store)
    assert report["summary"]["total_memories"] == 1
    assert store.get_memory("M1")["decay_factor"] <= 0.85


# ── recording ──────────────────────────────────────────────────────────
def test_record_outcome_writes_observations(store):
    _add(store, "M1", tags=["mysql"])
    counts = record_outcome(loop_id="L1", outcome="success", quality_score=1.0, memories_used=["M1"], store=store)
    assert counts["observations_recorded"] == 2  # loop-level + M1
    assert store.get_memory("M1")["observation_count"] == 1
    assert counts["candidates_created"] == 0


def test_record_failure_creates_candidate(store):
    _add(store, "M1")
    counts = record_outcome(loop_id="L1", outcome="failure", quality_score=0.0, memories_used=["M1"], store=store)
    assert counts["candidates_created"] == 1
    candidate = store.list_candidates()[0]
    assert candidate["candidate_type"] == "weaken"
    assert candidate["target_memory"] == "M1"


def test_record_high_quality_success_creates_candidate(store):
    _add(store, "M1")
    counts = record_outcome(loop_id="L1", outcome="success", quality_score=4.0, memories_used=["M1"], store=store)
    assert counts["candidates_created"] == 1
    candidate = store.list_candidates()[0]
    assert candidate["candidate_type"] == "reinforce"
    assert candidate["target_memory"] == "M1"


def test_usage_stats_track_success_rate(store):
    _add(store, "M1")
    record_outcome(loop_id="L1", outcome="success", memories_used=["M1"], store=store)
    record_outcome(loop_id="L2", outcome="failure", memories_used=["M1"], store=store)
    stats = store.usage_stats()["M1"]
    assert stats["usage_count"] == 2
    assert stats["successful_uses"] == 1
    assert stats["success_rate"] == 0.5
