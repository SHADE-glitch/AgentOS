"""Loop lifecycle tests: preflight, run, host postflight, idempotency."""

from __future__ import annotations

import subprocess

import pytest

from aos.adapters import base as adapters_base
from aos.adapters.test_provider import get_provider as get_test_provider
from aos.contract import validate_postflight, validate_preflight
from aos.core.loop import lifecycle
from aos.core.loop.state import LoopState
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
            "type": "procedural",
            "category": "backend",
            "title": "null pointer guard",
            "body": "check for null before dereferencing",
            "evidence_level": "runtime_validated",
            "status": "active",
        },
        tags=["null", "crash", "parser"],
    )
    doc = lifecycle.preflight(task="fix the null pointer crash in the parser", cwd=str(repo))

    ids = [m["memory_id"] for m in doc["memory"]["memories"]]
    assert "M1" in ids


def test_preflight_ships_the_rendered_injection_block(repo, store):
    """The block a host pushes must be produced by preflight, not just declared.

    A contract key that no producer fills is how ``skills_loaded`` ended up a
    validated field that is always empty, so this pins the seam itself.
    """
    store.upsert_memory(
        {
            "memory_id": "M1",
            "type": "procedural",
            "category": "backend",
            "title": "null pointer guard",
            "body": "check for null before dereferencing",
            "evidence_level": "runtime_validated",
            "status": "active",
        },
        tags=["null", "crash", "parser"],
    )
    doc = lifecycle.preflight(task="fix the null pointer crash in the parser", cwd=str(repo))

    injection = doc["memory"]["injection"]
    assert doc["memory"]["status"] == "ok"
    assert "<agent_os>" in injection["text"]
    assert "check for null before dereferencing" in injection["text"]
    assert injection["memory_ids"] == ["M1"]
    assert injection["char_count"] == len(injection["text"])
    assert [item["memory_id"] for item in injection["structured"]] == ["M1"]
    # The trimmed contract view and the block agree about what was recalled.
    assert injection["structured"][0]["body"] == doc["memory"]["memories"][0]["content"]


def test_preflight_persists_the_injection_size_for_later_proof(repo, store):
    """The loop file must carry the number that pairs with what the host appended.

    `pending-<session>.json` holds the injection size only until the postflight
    clears it, so the one durable witness that "the block the engine built is the
    block the host was handed" would evaporate with the run it describes. Measured
    on the first live host run: the plugin reported `len=1122`, and nothing on the
    engine side could be compared against it afterwards.
    """
    from aos.core.loop.state import LoopState

    store.upsert_memory(
        {
            "memory_id": "M1",
            "type": "procedural",
            "category": "backend",
            "title": "null pointer guard",
            "body": "check for null before dereferencing",
            "evidence_level": "runtime_validated",
            "status": "active",
        },
        tags=["null", "crash", "parser"],
    )
    doc = lifecycle.preflight(task="fix the null pointer crash in the parser", cwd=str(repo))

    state = LoopState.load(doc["loop_id"])
    recall = state.stage_data("recall")
    assert recall["injection_chars"] == doc["memory"]["injection"]["char_count"]
    assert recall["injected_memory_ids"] == doc["memory"]["injection"]["memory_ids"]


def test_preflight_reports_recall_as_skipped_when_memory_is_off(repo, store):
    store.upsert_memory(
        {"memory_id": "M1", "type": "procedural", "title": "t", "body": "b",
         "evidence_level": "runtime_validated", "tags": []},
        tags=["crash"],
    )
    doc = lifecycle.preflight(
        task="fix the null pointer crash", cwd=str(repo), memory_mode="disabled"
    )

    assert doc["memory"]["status"] == "skipped"
    # Skipped means nothing pushed, not an empty section for the host to inject.
    assert doc["memory"]["injection"]["text"] == ""
    assert "memory disabled by request" in doc["warnings"]


def test_preflight_echoes_a_declared_1_0_version(repo):
    doc = lifecycle.preflight(task="fix the crash", cwd=str(repo), schema_version="1.0")
    assert doc["schema_version"] == "1.0"
    validate_preflight(doc)


# ── run ────────────────────────────────────────────────────────────────
def test_run_without_evidence_is_partial_and_asks(repo):
    """A provider that answered is not a provider that was right.

    Nothing in this run reported a test, a build or a diff, so the engine says it
    does not know and queues the run for a label. It used to answer ``completed``,
    which is the constant that made the learning signal meaningless.
    """
    doc = lifecycle.run(task="add a health check endpoint", cwd=str(repo), provider="test_provider")

    validate_postflight(doc)
    assert doc["final_status"] == "partial"
    assert doc["learning"]["needs_review"] is True
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


def test_run_failing_tests_marks_failure(repo):
    """A non-zero test exit code is decisive, not an average.

    `partial` used to be the answer here because the loop only looked at the
    provider's own status; the tests failing is the strongest fact in the payload.
    """
    doc = lifecycle.run(
        task="add a health check endpoint",
        cwd=str(repo),
        provider="test_provider",
        test_command="pytest",
        test_exit_code=1,
    )

    assert doc["final_status"] == "failed"
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
    # Exact equality, not a superset: a provider that *drives* the host would
    # satisfy `>=` and quietly re-open the direction the boundary closed.
    assert set(adapters_base.available()) == {"host_delegate", "test_provider"}
    assert adapters_base.get("test_provider").name == "test_provider"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        adapters_base.get("does_not_exist")


# ── P5: a stage that fails must stay failed, and a stage that breaks must say so ──
def test_a_failed_execution_is_recorded_as_failed(repo):
    """The old sequence called complete() right after fail(), erasing the only record.

    This is the failure the learning loop was blind to: the engine's own error was
    rewritten into a completed stage while the payload still said it errored.
    """
    get_test_provider().set_scenario("provider_error")

    doc = lifecycle.run(task="add a health check endpoint", cwd=str(repo), provider="test_provider")

    state = LoopState.load(doc["loop_id"])
    entry = state.stages["execute"]
    assert entry["status"] == "failed", "the stage reports what happened, not what would be tidy"
    assert entry["error"]
    assert entry["data"], "the payload is still recorded — failing is not losing the evidence"
    assert any(e["stage"] == "execute" for e in state.errors)


def test_recall_failure_degrades_and_explains_itself(repo, monkeypatch):
    """`Never fatal` was a docstring with no try/except behind it.

    The loop must still hand the host a usable document — that part of the
    contract is right — but a broken recall has to be named, not swallowed into a
    generic preflight failure and certainly not reported as a clean `ok`.
    """
    def boom(*args, **kwargs):
        raise RuntimeError("store is on fire")

    monkeypatch.setattr("aos.core.loop.stages.retrieve", boom)

    doc = lifecycle.preflight(task="fix the null pointer crash", cwd=str(repo))

    assert doc["memory"]["status"] == "degraded"
    assert doc["memory"]["retrieved"] == 0
    assert any("recall failed" in w for w in doc["warnings"]), "the host must be told why"
    validate_preflight(doc)


def test_recall_failure_keeps_the_loop_state_honest(repo, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr("aos.core.loop.stages.retrieve", boom)

    doc = lifecycle.preflight(task="fix the null pointer crash", cwd=str(repo))
    state = LoopState.load(doc["loop_id"])

    assert state.stages["recall"]["status"] == "failed"
    assert state.stage_data("recall")["error"]
    assert state.stage_data("recall")["retrieved"] == 0
