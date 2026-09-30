"""Decompose a team plan into per-role task cards.

Ported from ``runtime/collaboration/task_decomposer.py``. One card per role;
the lead gets the whole task, support roles get a scoped description. Card
dependencies come from the team plan's advisory role dependencies.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from aos.core.orchestration.orchestrator import TeamPlan


@dataclass
class TaskCard:
    task_id: str
    team_id: str
    role: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    is_lead: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ready_to_run(self, completed_tasks: set[str]) -> bool:
        return self.status == "pending" and set(self.dependencies).issubset(completed_tasks)


class TaskDecomposer:
    def decompose(self, task: str, team_plan: TeamPlan) -> list[TaskCard]:
        all_roles = [team_plan.lead_agent] + list(team_plan.support_agents)
        role_to_task: dict[str, str] = {}
        cards: list[TaskCard] = []

        for role in all_roles:
            task_id = self._task_id(role, team_plan.team_id)
            role_to_task[role] = task_id
            is_lead = role == team_plan.lead_agent
            cards.append(
                TaskCard(
                    task_id=task_id,
                    team_id=team_plan.team_id,
                    role=role,
                    description=self._describe(role, task, team_plan, is_lead),
                    is_lead=is_lead,
                )
            )

        dependency_map = {d["role"]: d["depends_on"] for d in team_plan.dependencies}
        for card in cards:
            card.dependencies = [
                role_to_task[role]
                for role in dependency_map.get(card.role, [])
                if role in role_to_task and role != card.role
            ]
        return cards

    def _task_id(self, role: str, team_id: str) -> str:
        digest = hashlib.md5(f"{team_id}:{role}".encode("utf-8")).hexdigest()[:6]
        return f"task-{role}-{digest}"

    def _describe(self, role: str, task: str, team_plan: TeamPlan, is_lead: bool) -> str:
        if is_lead:
            return (
                f"[LEAD] {task}\n\n"
                f"You lead team {team_plan.team_id}.\n"
                f"Domains: {', '.join(team_plan.domains) or 'none'}.\n"
                "Coordinate the support agents and produce the final result."
            )
        return (
            f"[SUPPORT] Contribute to: {task}\n\n"
            f"Team: {team_plan.team_id}\n"
            f"Your role: {role}\n"
            "Focus on your domain expertise and produce output for lead review."
        )


def decompose(task: str, team_plan: TeamPlan) -> list[TaskCard]:
    return TaskDecomposer().decompose(task, team_plan)
