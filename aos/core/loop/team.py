"""Executor / team metadata for a loop.

Thin adapter over the orchestration rules: it asks the orchestrator to form a
team, then decomposes that team into task cards. A single-agent task degrades
cleanly to an empty card list.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from aos.core.orchestration.collaboration import decompose
from aos.core.orchestration.orchestrator import form_team


@dataclass
class ExecutorPlan:
    """How a loop's work will be carried out."""

    is_multi_agent: bool
    lead_role: str
    support_roles: list[str] = field(default_factory=list)
    team_id: str = ""
    rationale: str = ""
    rules_applied: list[str] = field(default_factory=list)
    pruned_roles: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    task_cards: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_executor(
    *,
    task: str = "",
    lead_role: str,
    support_roles: list[str],
    domains: list[str],
    difficulty: str = "medium",
    intent: str = "",
) -> ExecutorPlan:
    """Form a team and decompose it into per-role task cards."""
    team = form_team(
        task,
        lead_role=lead_role,
        support_roles=support_roles,
        domains=domains,
        intent=intent,
        difficulty=difficulty,
    )
    cards = [card.to_dict() for card in decompose(task, team)] if team.is_multi_agent else []
    return ExecutorPlan(
        is_multi_agent=team.is_multi_agent,
        lead_role=team.lead_agent,
        support_roles=list(team.support_agents),
        team_id=team.team_id,
        rationale=team.reasoning,
        rules_applied=list(team.rules_applied),
        pruned_roles=list(team.pruned_roles),
        dependencies=list(team.dependencies),
        task_cards=cards,
    )
