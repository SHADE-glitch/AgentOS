"""Orchestration and collaboration tests."""

from __future__ import annotations

import json

from aos.config import get_paths
from aos.core.loop import stages
from aos.core.loop.state import LoopState
from aos.core.loop.team import plan_executor
from aos.core.orchestration import orchestrator as orch
from aos.core.orchestration.collaboration import (
    Aggregator,
    Scheduler,
    TaskCard,
    decompose,
    stub_agent_executor,
)
from aos.core.routing import taxonomy


def _team(**kwargs):
    defaults = dict(
        task="do the thing",
        lead_role="code-reviewer",
        support_roles=[],
        domains=["backend"],
        intent="coding",
        difficulty="medium",
    )
    defaults.update(kwargs)
    return orch.form_team(**defaults)


# ── activation ─────────────────────────────────────────────────────────
def test_single_domain_medium_does_not_form_team():
    assert orch.should_form_team(domains=["backend"], difficulty="medium", intent="coding") is False


def test_two_domains_forms_team():
    assert orch.should_form_team(domains=["backend", "database"], difficulty="medium", intent="coding") is True


def test_hard_difficulty_forms_team():
    assert orch.should_form_team(domains=["backend"], difficulty="hard", intent="coding") is True


def test_architecture_intent_forms_team():
    assert orch.should_form_team(domains=["backend"], difficulty="medium", intent="architecture") is True


def test_learning_intent_never_forms_team():
    assert orch.should_form_team(domains=["backend", "ai"], difficulty="hard", intent="learning") is False


# ── team formation rules ───────────────────────────────────────────────
def test_single_agent_degrades_cleanly():
    team = _team()
    assert team.is_multi_agent is False
    assert team.lead_agent == "code-reviewer"
    assert team.support_agents == []


def test_r1_cross_domain_augmentation():
    team = _team(domains=["backend", "database"], difficulty="hard")
    assert team.is_multi_agent is True
    assert "database-engineer" in team.support_agents
    assert any(r.startswith("R1") for r in team.rules_applied)


def test_r2_architecture_adds_system_architect():
    team = _team(intent="architecture")
    assert "system-architect" in team.support_agents


def test_r4_rag_and_r5_llm_roles():
    team = _team(
        task="build a RAG pipeline over documents with an LLM",
        lead_role="llm-engineer",
        domains=["ai", "backend"],
        difficulty="hard",
    )
    assert "rag-engineer" in team.support_agents


def test_r9_security_domain_adds_security_engineer():
    team = _team(domains=["security", "backend"], difficulty="hard")
    assert "security-engineer" in team.support_agents


def test_every_selected_role_is_in_the_catalog():
    catalog = set(taxonomy.role_catalog())
    for domains, intent, difficulty in [
        (["backend", "database"], "coding", "hard"),
        (["frontend", "backend"], "architecture", "medium"),
        (["ai", "security"], "coding", "hard"),
        (["distributed", "database"], "testing", "hard"),
    ]:
        team = _team(domains=domains, intent=intent, difficulty=difficulty)
        assert {team.lead_agent, *team.support_agents} <= catalog


def test_unknown_roles_are_pruned_and_recorded():
    team = _team(domains=["backend", "database"], difficulty="hard", support_roles=["not-a-real-role"])
    assert "not-a-real-role" not in team.support_agents
    assert any(p["role"] == "not-a-real-role" and p["reason"] == "not_in_registry" for p in team.pruned_roles)


def test_team_size_cap_is_enforced():
    rules = orch.load_rules()
    rules["conflict_rules"]["max_team_size"] = 2
    team = orch.form_team(
        "big task",
        lead_role="code-reviewer",
        support_roles=[],
        domains=["backend", "database", "security", "frontend"],
        intent="architecture",
        difficulty="hard",
        rules=rules,
    )
    assert len(team.support_agents) + 1 <= 2
    assert any(p["reason"] == "team_size_cap" for p in team.pruned_roles)


def test_dependencies_only_reference_teammates():
    team = _team(domains=["backend", "database", "testing"], intent="testing", difficulty="hard")
    teammates = {team.lead_agent, *team.support_agents}
    for dependency in team.dependencies:
        assert dependency["role"] in teammates
        assert set(dependency["depends_on"]) <= teammates


# ── rules are data, not code ───────────────────────────────────────────
def test_rules_can_be_overridden_by_the_content_layer():
    policies = get_paths().policies_dir
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "orchestration.json").write_text(
        json.dumps({"activation_rules": {"domain_threshold": 99, "trigger_on_hard": False, "trigger_intents": []}}),
        encoding="utf-8",
    )
    orch.reload()
    try:
        assert orch.should_form_team(domains=["a", "b", "c"], difficulty="hard", intent="architecture") is False
    finally:
        (policies / "orchestration.json").unlink()


# ── collaboration ──────────────────────────────────────────────────────
def test_decompose_creates_one_card_per_role():
    team = _team(domains=["backend", "database"], difficulty="hard")
    cards = decompose("migrate the schema", team)

    assert len(cards) == 1 + len(team.support_agents)
    leads = [c for c in cards if c.is_lead]
    assert len(leads) == 1
    assert leads[0].role == team.lead_agent
    assert all(c.task_id for c in cards)


def test_decompose_resolves_dependencies_to_task_ids():
    team = _team(domains=["backend", "database"], difficulty="hard")
    cards = decompose("migrate the schema", team)
    ids = {c.task_id for c in cards}
    for card in cards:
        assert set(card.dependencies) <= ids
        assert card.task_id not in card.dependencies


def test_scheduler_runs_in_dependency_order():
    a = TaskCard(task_id="a", team_id="t", role="lead", description="lead", is_lead=True)
    b = TaskCard(task_id="b", team_id="t", role="support", description="support", dependencies=["a"])
    result = Scheduler().execute([b, a])

    assert result["execution_order"] == ["a", "b"]
    assert set(result["completed"]) == {"a", "b"}
    assert result["trace"].events_by_type("result_aggregated")


def test_scheduler_marks_failed_agent():
    def boom(card, context):
        if card.role == "support":
            return {"status": "failed", "error": "nope"}
        return stub_agent_executor(card, context)

    a = TaskCard(task_id="a", team_id="t", role="lead", description="lead", is_lead=True)
    b = TaskCard(task_id="b", team_id="t", role="support", description="support")
    result = Scheduler(agent_executor=boom).execute([a, b])

    assert result["failed"] == ["b"]


def test_scheduler_detects_unresolved_dependency():
    card = TaskCard(task_id="a", team_id="t", role="lead", description="x", dependencies=["missing"])
    result = Scheduler().execute([card])
    assert result["failed"] == ["a"]


def test_scheduler_validate_dependencies():
    card = TaskCard(task_id="a", team_id="t", role="lead", description="x", dependencies=["a", "ghost"])
    problems = Scheduler().validate_dependencies([card])
    kinds = {p["problem"] for p in problems}
    assert "self_dependency" in kinds
    assert "missing_dependency" in kinds


def test_aggregator_lead_has_authority():
    lead = TaskCard(task_id="a", team_id="t", role="lead", description="x", is_lead=True)
    lead.status = "completed"
    lead.output_data = {"output": "final"}
    support = TaskCard(task_id="b", team_id="t", role="support", description="y")
    support.status = "completed"
    support.output_data = {"output": "contribution"}

    result = Aggregator().aggregate([lead, support])

    assert result.status == "success"
    assert result.lead_output == {"output": "final"}
    assert result.completed_count == 2
    assert len(result.contributions) == 2


def test_aggregator_reports_partial_when_a_card_fails():
    lead = TaskCard(task_id="a", team_id="t", role="lead", description="x", is_lead=True)
    lead.status = "completed"
    failed = TaskCard(task_id="b", team_id="t", role="support", description="y")
    failed.status = "failed"

    result = Aggregator().aggregate([lead, failed])
    assert result.status == "partial"
    assert result.failed_count == 1


def test_aggregator_flags_explicit_conflicts():
    one = TaskCard(task_id="a", team_id="t", role="r1", description="x")
    one.status = "completed"
    one.output_data = {"conflicts_with": "r2", "conflict_detail": "opposite advice"}
    two = TaskCard(task_id="b", team_id="t", role="r2", description="y")
    two.status = "completed"
    two.output_data = {}

    result = Aggregator().aggregate([one, two])
    assert result.conflicts and result.conflicts[0]["agents"] == ["r1", "r2"]


# ── loop integration ───────────────────────────────────────────────────
def test_plan_executor_is_single_agent_for_a_simple_task():
    plan = plan_executor(
        task="fix the null pointer crash",
        lead_role="code-reviewer",
        support_roles=[],
        domains=["bugfix"],
        difficulty="medium",
        intent="bugfix",
    )
    assert plan.is_multi_agent is False
    assert plan.task_cards == []


def test_plan_executor_forms_a_team_for_a_cross_domain_task():
    plan = plan_executor(
        task="add a database index and secure the API",
        lead_role="backend-architect",
        support_roles=[],
        domains=["backend", "database", "security"],
        difficulty="hard",
        intent="coding",
    )
    assert plan.is_multi_agent is True
    assert plan.team_id
    assert plan.task_cards
    assert all(card["team_id"] == plan.team_id for card in plan.task_cards)


def test_loop_resolve_role_stage_records_the_team():
    state = LoopState.new(task_text="add a database index and secure the API")
    decision = {
        "lead_role": "backend-architect",
        "support_roles": [],
        "domains": ["backend", "database", "security"],
        "difficulty": "hard",
        "intent": "coding",
    }
    result = stages.resolve_role_stage(state, decision)

    assert result["executor"]["is_multi_agent"] is True
    assert state.stage_data("resolve_role")["executor"]["task_cards"]
