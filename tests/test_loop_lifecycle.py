"""Loop lifecycle tests: preflight, run, host postflight, idempotency."""

from __future__ import annotations

import subprocess

import pytest

from aos.adapters import base as adapters_base
from aos.adapters.test_provider import get_provider as get_test_provider
from aos.contract import validate_postflight, validate_preflight
from aos.core.loop import lifecycle
from aos.core.memory.store import MemoryStore


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=path,
        check=True,
    )
    return path


@pytest.fixture(autouse=True)
def _reset_providers():
    get_test_provider().reset()
    adapters_base.reset()
    yield
    get_test_provider().reset()
    adapters_base.reset()


@pytest.fixture
def repo(tmp_path):
    return _init_repo(tmp_path / "proj")


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


# ── preflight ──────────────────────────────────────────────────────────
def test_preflight_returns_valid_contract(repo):
    doc = lifecycle.preflight(task="fix the null pointer crash in the parser", cwd=str(repo))

    validate_preflight(doc)
    assert doc["router"]["lead_skill"]
    assert doc["router"]["lead_role"]
    assert doc["artifacts"]["loop_state"].endswith(f"{doc['loop_id']}.json")


def test_preflight_persists_loop_state(repo):
    doc = lifecycle.preflight(task="fix the null pointer crash", cwd=str(repo))
    from aos.core.loop.state import LoopState

    state = LoopState.load(doc["loop_id"])
    assert state is not None
    assert state.task_id == doc["task_id"]
    assert state.stages["route"]["status"] == "completed"
    assert state.stages["recall"]["status"] == "completed"


def test_preflight_recalls_seeded_memory(repo, store):
    store.upsert_memory(
        {
            "memory_id": "M1",
            "type": "pattern",
            "category": "backend",
            "title": "null pointer guard",
            "body": "check for null before dereferencing",
            "evidence_level": "runtime_validated",
        },
        tags=["null", "crash", "parser"],
    )
    doc = lifecycle.preflight(task="fix the null pointer crash in the parser", cwd=str(repo))

    ids = [m["memory_id"] for m in doc["memory"]["memories"]]
    assert "M1" in ids


# ── run ────────────────────────────────────────────────────────────────
def test_run_with_test_provider_completes(repo):
    doc = lifecycle.run(task="add a health check endpoint", cwd=str(repo), provider="test_provider")

    validate_postflight(doc)
    assert doc["final_status"] == "completed"
    assert doc["evidence"]["repo_resolved"] is True


def test_run_writes_observations_and_runs_evolve(repo, store):
    doc = lifecycle.run(task="add a health check endpoint", cwd=str(repo), provider="test_provider")

    observations = store.list_observations()
    assert any(o["loop_id"] == doc["loop_id"] for o in observations)
    assert store.list_events(event_type="learning.run")


def test_run_provider_error_marks_failed(repo):
    get_test_provider().set_scenario("provider_error")

    doc = lifecycle.run(task="add a health check endpoint", cwd=str(repo), provider="test_provider")

    assert doc["final_status"] == "failed"
    assert doc["recovery"]["failures_detected"] >= 1
    assert doc["recovery"]["plan"]["recovery_needed"] is True


def test_run_failing_tests_marks_partial(repo):
    doc = lifecycle.run(
        task="add a health check endpoint",
        cwd=str(repo),
        provider="test_provider",
        test_command="pytest",
        test_exit_code=1,
    )

    assert doc["final_status"] == "partial"
    assert doc["evidence"]["test_passed"] is False


def test_delegated_run_is_partial(repo):
    doc = lifecycle.run(task="add a health check endpoint", cwd=str(repo), provider="host_delegate")
    assert doc["final_status"] == "partial"


# ── host-style postflight ──────────────────────────────────────────────
def test_host_postflight_closes_the_learning_loop(repo, store):
    pre = lifecycle.preflight(task="refactor the router", cwd=str(repo), provider="host_delegate")

    doc = lifecycle.postflight(
        task_id=pre["task_id"],
        loop_id=pre["loop_id"],
        cwd=str(repo),
        outcome="success",
        quality_score=4.0,
    )

    validate_postflight(doc)
    assert store.list_events(event_type="learning.run")
    assert any(o["loop_id"] == pre["loop_id"] for o in store.list_observations())


def test_postflight_is_idempotent(repo):
    pre = lifecycle.preflight(task="refactor the router", cwd=str(repo))
    first = lifecycle.postflight(task_id=pre["task_id"], loop_id=pre["loop_id"], cwd=str(repo))
    second = lifecycle.postflight(task_id=pre["task_id"], loop_id=pre["loop_id"], cwd=str(repo))

    assert first["replayed"] is False
    assert second["replayed"] is True
    assert second["final_status"] == first["final_status"]


def test_postflight_unknown_loop_falls_back():
    doc = lifecycle.postflight(task_id="HOST-XXXX", loop_id="LOOP-NOPE")
    validate_postflight(doc)
    assert doc["aos_status"] == "fallback"


# ── provider registry ──────────────────────────────────────────────────
def test_provider_registry_lists_builtins():
    assert set(adapters_base.available()) >= {"opencode", "host_delegate", "test_provider"}
    assert adapters_base.get("test_provider").name == "test_provider"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        adapters_base.get("does_not_exist")
