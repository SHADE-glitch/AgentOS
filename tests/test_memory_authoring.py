"""Authoring and cold-start seed tests.

Cold start is the breakpoint that hid all the others: with zero memories,
recall is empty, so no candidates, so learning has nothing to iterate over —
and every downstream fix is observationally identical to no fix at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aos.contract.schema import MEMORY_TYPE
from aos.core.memory import authoring
from aos.core.memory.authoring import AuthoringError, new_memory, seed_from_dir, seed_id
from aos.core.memory.evolve import EVIDENCE_LEVELS
from aos.core.memory.inject import render
from aos.core.memory.policy import load_policy
from aos.core.memory.store import MemoryStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SEED = REPO_ROOT / "content" / "memory" / "seed" / "agentos.json"


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


def _write_seed(directory: Path, memories, **extra) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "seed.json"
    path.write_text(json.dumps({"memories": memories, **extra}), encoding="utf-8")
    return path


def _entry(memory_id="M-AAA", **overrides) -> dict:
    entry = {
        "memory_id": memory_id,
        "title": "run the suite before promoting a memory",
        "body": "promote only after tests pass; a green render is not a green run.",
        "type": "procedural",
        "category": "test",
        "tags": ["learning"],
        "roles": ["testing-engineer"],
        "evidence_level": "runtime_validated",
        "confidence": "high",
        "verified": True,
    }
    entry.update(overrides)
    return entry


# ── new_memory validation ──────────────────────────────────────────────
def test_a_plainly_authored_memory_is_storable(store):
    row = new_memory(title="check the null before dereferencing", body="guard at the boundary.")
    store.upsert_memory(row, tags=row["tags"], roles=row["roles"])
    assert store.get_memory(row["memory_id"])["title"] == "check the null before dereferencing"


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"title": ""}, "title must not be empty"),
        ({"title": "x" * 121}, "the cap is 120"),
        ({"body": ""}, "body must not be empty"),
        ({"body": "y" * 2001}, "the cap is 2000"),
        ({"type": "anecdote"}, "is not one of"),
        ({"evidence_level": "guessed"}, "is not one of"),
        ({"confidence": "certain"}, "is not one of"),
        ({"status": "forgotten"}, "is not one of"),
    ],
)
def test_invalid_fields_are_rejected_before_storage(overrides, fragment):
    kwargs = {k: v for k, v in _entry(**overrides).items() if k != "verified"}
    with pytest.raises(AuthoringError) as excinfo:
        new_memory(**kwargs, verified=overrides.pop("verified", False))
    assert fragment in str(excinfo.value)


def test_whitespace_is_normalised_so_layout_cannot_split_a_fact():
    row = new_memory(title="  guard   at\nthe boundary ", body="check   first.\nthen  act.")
    assert row["title"] == "guard at the boundary"
    assert row["body"] == "check first. then act."


def test_enums_agree_with_the_contract_and_the_ladder():
    for type_ in MEMORY_TYPE:
        assert new_memory(title="t", body="b", type=type_, verified=True)["type"] == type_
    for level in EVIDENCE_LEVELS:
        assert (
            new_memory(title="t", body="b", evidence_level=level, verified=True)["evidence_level"]
            == level
        )


# ── the verified gate ──────────────────────────────────────────────────
def test_an_unverified_claim_is_demoted_to_a_hypothesis():
    row = new_memory(
        title="t",
        body="b",
        evidence_level="production_validated",
        confidence="high",
    )
    assert row["evidence_level"] == "hypothesis"
    assert row["confidence"] == "low"


def test_authoring_a_memory_alone_can_never_claim_verified_evidence():
    """The renderer must still label a hand-written memory as unverified.

    This is the one place an author could shortcut the evidence ladder, so the
    assertion is on the rendered block rather than only on the stored fields.
    """
    row = new_memory(title="t", body="b", evidence_level="production_validated")
    block = render([row])["text"]
    assert "未验证，仅作提示" in block


def test_declaring_verified_keeps_the_evidence_level():
    row = new_memory(title="t", body="b", evidence_level="runtime_validated", verified=True)
    assert row["evidence_level"] == "runtime_validated"


# ── the lifecycle gate at birth ────────────────────────────────────────
def test_an_unverified_memory_is_born_a_candidate_in_the_hypothesis_lane():
    row = new_memory(title="t", body="b", evidence_level="production_validated")
    assert row["status"] == "candidate"
    assert row["lane"] == "hypothesis"
    assert row["last_verified_at"] == ""


def test_no_one_can_author_a_memory_straight_into_verified():
    """The status argument is not a way to skip the evidence ladder.

    ``verified`` without evidence is exactly how a store fills up with claims
    nothing confirmed, and every later ranking then treats them as established.
    """
    row = new_memory(title="t", body="b", status="verified")
    assert row["status"] == "candidate"


def test_an_unknown_status_is_rejected_even_when_it_would_be_overridden():
    with pytest.raises(AuthoringError):
        new_memory(title="t", body="b", status="forgotten")


def test_a_verified_memory_is_born_active_and_stamped_when():
    row = new_memory(title="t", body="b", evidence_level="runtime_validated", verified=True)
    assert row["status"] == "active"
    assert row["lane"] == "standard"
    assert row["last_verified_at"].startswith("20")


def test_a_verified_but_hypothesis_levelled_memory_stays_in_the_lane():
    row = new_memory(title="t", body="b", evidence_level="hypothesis", verified=True)
    assert row["lane"] == "hypothesis"


@pytest.mark.parametrize("scope", ["global", "project:AgentOS", "session:s-1"])
def test_the_three_scope_shapes_are_accepted(scope):
    assert new_memory(title="t", body="b", scope=scope)["scope"] == scope


@pytest.mark.parametrize("scope", ["", "project:", "whole-world", "AgentOS"])
def test_a_scope_that_cannot_be_filtered_on_is_rejected(scope):
    """`project:` with no id would be recalled by nothing and hidden from nothing."""
    with pytest.raises(AuthoringError):
        new_memory(title="t", body="b", scope=scope)


def test_the_trigger_clause_and_scope_survive_into_the_store(store):
    """The two fields the lifecycle added must round-trip, not just validate.

    ``when_to_apply`` is what turns a fact into something the model knows when to
    use, and ``scope`` is what keeps a Java fact out of a JavaScript task; either
    one silently dropped would leave the schema looking richer than the recall is.
    """
    row = new_memory(
        title="pin the token order first",
        body="fix the verification order before touching the signature.",
        type="procedural",
        scope="project:AgentOS",
        when_to_apply="editing the auth middleware",
        revalidate_after="2027-01-31",
        verified=True,
    )
    store.upsert_memory(row, tags=row["tags"], roles=row["roles"])
    stored = store.get_memory(row["memory_id"])
    assert stored["scope"] == "project:AgentOS"
    assert stored["when_to_apply"] == "editing the auth middleware"
    assert stored["revalidate_after"] == "2027-01-31"

    block = render([stored])["text"]
    assert "适用：editing the auth middleware" in block
    assert "做法：fix the verification order" in block


def test_the_six_types_render_six_different_shapes():
    """A type that did not change the sentence would not be worth having."""
    prefixes = {
        type_: render([new_memory(title="t", body="b", type=type_, verified=True)])["text"]
        for type_ in MEMORY_TYPE
    }
    for type_, text in prefixes.items():
        assert any(word in text for word in ("不要：", "做法：", "经过：", "事实：", "偏好：", "约束：")), type_
    assert "约束：" in prefixes["constraint"]
    assert "不要：" in prefixes["failure"]
    assert "经过：" in prefixes["episodic"]


# ── ids ────────────────────────────────────────────────────────────────
def test_derived_ids_are_content_based_and_stable():
    assert seed_id("Guard at the boundary", "check first.") == seed_id(
        "  guard   at\nthe boundary", "check  first."
    )
    assert seed_id("a", "b") != seed_id("a", "c")


def test_an_explicit_id_wins_over_the_derived_one():
    assert new_memory(title="t", body="b", memory_id="M-SEED-X1")["memory_id"] == "M-SEED-X1"


def test_reseeding_the_same_derived_id_does_not_duplicate(store):
    first = new_memory(title="guard at the boundary", body="check first.")
    second = new_memory(title="guard at the boundary", body="check first.")
    store.upsert_memory(first, tags=[], roles=[])
    store.upsert_memory(second, tags=[], roles=[])
    assert first["memory_id"] == second["memory_id"]
    assert store.count_memories() == 1


def test_tags_and_roles_are_stripped_and_empties_dropped():
    row = new_memory(title="t", body="b", tags=[" auth ", "", "middleware"], roles=["  ", "x"])
    assert row["tags"] == ["auth", "middleware"]
    assert row["roles"] == ["x"]


def test_authored_tags_reach_the_recall_path():
    """Read back through ``memories_for_scoring``, the shape recall consumes.

    ``get_memory`` returns the bare ``memories`` row, so asserting tags there
    would pass even if the tag insert were dropped — and tags are the 0.40
    weight term, the largest single one.
    """
    s = MemoryStore()
    try:
        row = new_memory(title="t", body="b", tags=["cache-key"], roles=["backend-architect"])
        s.upsert_memory(row, tags=row["tags"], roles=row["roles"])
        scored = {m["memory_id"]: m for m in s.memories_for_scoring()}[row["memory_id"]]
        assert scored["tags"] == ["cache-key"]
        assert scored["roles"] == ["backend-architect"]
    finally:
        s.close()


# ── seed_from_dir ──────────────────────────────────────────────────────
def test_seed_loads_a_nested_directory(tmp_path, store):
    _write_seed(tmp_path / "seed", [_entry("M-A"), _entry("M-B", title="other")])
    report = seed_from_dir(tmp_path, store=store)
    assert sorted(report["seeded"]) == ["M-A", "M-B"]
    assert report["errors"] == []
    assert store.count_memories() == 2


def test_seed_is_idempotent_and_never_reverts_a_human_edit(tmp_path, store):
    entry = _entry("M-A")
    _write_seed(tmp_path, [entry])
    seed_from_dir(tmp_path, store=store)

    refined = dict(store.get_memory("M-A"))
    refined["body"] = "rewritten by a reviewer who ran the experiment"
    store.upsert_memory(refined, tags=list(entry["tags"]), roles=list(entry["roles"]))

    report = seed_from_dir(tmp_path, store=store)
    assert report["seeded"] == []
    assert report["skipped"] == ["M-A"]
    assert store.get_memory("M-A")["body"] == "rewritten by a reviewer who ran the experiment"


def test_force_rewrites_deliberately(tmp_path, store):
    _write_seed(tmp_path, [_entry("M-A")])
    seed_from_dir(tmp_path, store=store)
    store.upsert_memory(
        {**store.get_memory("M-A"), "body": "hand edit"}, tags=[], roles=[]
    )

    report = seed_from_dir(tmp_path, store=store, force=True)
    assert report["seeded"] == ["M-A"]
    assert "promote only after tests pass" in store.get_memory("M-A")["body"]


def test_a_broken_entry_does_not_cost_the_whole_file(tmp_path, store):
    _write_seed(tmp_path, [_entry("M-GOOD"), _entry("M-BAD", type="anecdote")])
    report = seed_from_dir(tmp_path, store=store)
    assert report["seeded"] == ["M-GOOD"]
    assert len(report["errors"]) == 1
    assert "anecdote" in report["errors"][0]
    assert store.count_memories() == 1


def test_malformed_json_is_reported_with_the_filename(tmp_path, store):
    (tmp_path / "bad.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    report = seed_from_dir(tmp_path, store=store)
    assert report["seeded"] == []
    assert report["errors"][0].startswith("bad.json:")


def test_wrong_shape_is_reported(tmp_path, store):
    path = tmp_path / "shape.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    report = seed_from_dir(tmp_path, store=store)
    assert report["errors"][0].startswith("shape.json:")
    assert "must be a list" in report["errors"][0]


def test_a_top_level_list_is_accepted(tmp_path, store):
    path = tmp_path / "flat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([_entry("M-A"), _entry("M-B", title="other")]), encoding="utf-8")
    report = seed_from_dir(tmp_path, store=store)
    assert sorted(report["seeded"]) == ["M-A", "M-B"]


def test_prose_beside_memories_is_not_mistaken_for_one(tmp_path, store):
    _write_seed(tmp_path, [_entry("M-A")], note="These entries were verified in repo X.")
    report = seed_from_dir(tmp_path, store=store)
    assert store.count_memories() == 1
    assert report["seeded"] == ["M-A"]


def test_a_missing_directory_is_an_error_not_a_crash(tmp_path, store):
    report = seed_from_dir(tmp_path / "nope", store=store)
    assert report["errors"] == [f"no seed directory at {tmp_path / 'nope'}"]


def test_an_empty_directory_seeds_nothing(tmp_path, store):
    tmp_path.mkdir(parents=True, exist_ok=True)
    report = seed_from_dir(tmp_path, store=store)
    assert report == {"seeded": [], "skipped": [], "errors": [], "files": []}


# ── the shipped seed: the artifact a fresh install actually gets ───────
@pytest.fixture(scope="module")
def shipped_seed_entries() -> list[dict]:
    document = json.loads(SHIPPED_SEED.read_text(encoding="utf-8"))
    return document["memories"]


def test_the_shipped_seed_exists_and_is_not_empty(shipped_seed_entries):
    assert len(shipped_seed_entries) >= 6, "cold start must give recall something to find"


def test_the_shipped_seed_passes_authoring_validation(shipped_seed_entries):
    for entry in shipped_seed_entries:
        new_memory(
            **{k: v for k, v in entry.items() if k != "verified"},
            verified=bool(entry.get("verified", False)),
        )


def test_shipped_seed_entries_carry_their_evidence_level(shipped_seed_entries):
    """A seed claiming ``verified`` with no level would render as a hint anyway.

    The two flags must agree, or the block labels established facts as
    unverified guesses and the reader learns to ignore the section.
    """
    for entry in shipped_seed_entries:
        assert entry.get("verified") is True, entry["memory_id"]
        assert entry["evidence_level"] != "hypothesis", entry["memory_id"]


def test_every_seed_entry_states_its_rule_inside_the_budget(shipped_seed_entries):
    """Bodies lead with the rule because clipping cuts from the end.

    ``render`` truncates at ``max_body_chars`` on a whitespace boundary, so a
    lesson written as a narrative loses its conclusion first — the one part a
    model needs. The first sentence is therefore the contract.
    """
    limit = int(load_policy("injection")["max_body_chars"])
    for entry in shipped_seed_entries:
        rule = " ".join(entry["body"].split()).split("。")[0]
        assert len(rule) <= limit, f"{entry['memory_id']} buries its rule: {len(rule)} > {limit}"


def test_every_seed_entry_says_when_it_applies(shipped_seed_entries):
    """The file's own stated rule, asserted rather than trusted.

    A memory with no trigger clause reaches the model as an unmotivated fact and
    is either ignored or applied where it does not belong.
    """
    for entry in shipped_seed_entries:
        assert entry.get("when_to_apply"), entry["memory_id"]


def test_every_seed_entry_declares_a_scope_it_can_be_filtered_by(shipped_seed_entries):
    for entry in shipped_seed_entries:
        assert entry.get("scope"), entry["memory_id"]
        # Raises for a scope recall could never match, e.g. a bare `project:`.
        authoring.validate_scope(entry["scope"])


def test_a_fact_pinned_to_a_host_version_carries_an_expiry(shipped_seed_entries):
    """Entries citing an observed opencode behaviour must be re-checked.

    An invariant ("stdlib only") never expires; a claim about version 1.18.33
    does, and saying so is what stops it quietly becoming a permanent falsehood.
    """
    for entry in shipped_seed_entries:
        if "opencode 1.18" in entry["body"] or "opencode 插件" in entry["title"]:
            assert entry.get("revalidate_after"), f"{entry['memory_id']} pins a version but never expires"


def test_seed_ids_are_unique_and_prefixed(shipped_seed_entries):
    ids = [entry["memory_id"] for entry in shipped_seed_entries]
    assert len(ids) == len(set(ids))
    assert all(str(memory_id).startswith("M-SEED-") for memory_id in ids)


def test_the_shipped_seed_survives_a_round_trip_into_a_fresh_store(tmp_path, store):
    """The whole point of cold start: a new database becomes recallable.

    Asserted through ``render`` rather than the table, because the failure this
    phase found was a stored memory whose text never reached the block.
    """
    report = seed_from_dir(SHIPPED_SEED.parent, store=store)
    assert report["errors"] == []
    assert len(report["seeded"]) == len(json.loads(SHIPPED_SEED.read_text())["memories"])

    block = render(
        [
            {**store.get_memory(memory_id), "final_score": 1.0}
            for memory_id in report["seeded"][:3]
        ]
    )
    assert block["text"].startswith("<agent_os>")
    assert block["structured"][0]["body"]
    assert all(item["title"] for item in block["structured"])
