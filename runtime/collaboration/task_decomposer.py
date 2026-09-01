"""
Task Decomposer — Phase 8.1

Converts TeamPlan + task description into executable TaskCards.

Each TaskCard represents a unit of work for one agent role.
TaskCards carry dependency metadata for scheduler ordering.

Architecture:
  TeamPlan → TaskDecomposer.decompose() → List[TaskCard]
"""

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TaskCard:
    """A unit of work assigned to a single agent role."""
    task_id: str                    # "task-{role}-{hash[:6]}"
    team_id: str
    role: str                       # agent role name (e.g. "backend-architect")
    description: str                # what this agent should do
    dependencies: list = field(default_factory=list)   # task_ids this depends on
    status: str = "pending"         # pending | ready | running | completed | failed
    input_data: dict = field(default_factory=dict)     # data passed in
    output_data: dict = field(default_factory=dict)    # agent's output
    is_lead: bool = False           # whether this agent is the team lead

    def to_dict(self) -> dict:
        return asdict(self)

    def ready_to_run(self, completed_tasks: set) -> bool:
        """Check if all dependencies are satisfied."""
        return self.status == "pending" and set(self.dependencies).issubset(completed_tasks)


class TaskDecomposer:
    """
    Decomposes a TeamPlan into executable TaskCards.

    Rules:
      - One TaskCard per agent role (lead + supports)
      - Lead gets the full task description
      - Supports get domain-specific subtask descriptions
      - Dependencies from TeamPlan are converted to task_id references
    """

    def decompose(self, task: str, team_plan) -> list:
        """
        Convert TeamPlan into a list of TaskCards.

        Args:
            task: Original task description
            team_plan: TeamPlan from Orchestrator.form_team()

        Returns:
            List of TaskCard objects with dependency ordering
        """
        all_roles = [team_plan.lead_agent] + team_plan.support_agents
        role_to_task_id = {}

        # Phase 1: Create TaskCards and build role→task_id mapping
        cards = []
        for role in all_roles:
            task_id = self._generate_task_id(role, team_plan.team_id)
            role_to_task_id[role] = task_id
            is_lead = (role == team_plan.lead_agent)
            description = self._build_description(role, task, team_plan, is_lead)

            card = TaskCard(
                task_id=task_id,
                team_id=team_plan.team_id,
                role=role,
                description=description,
                is_lead=is_lead,
            )
            cards.append(card)

        # Phase 2: Resolve dependencies from TeamPlan to task_ids
        dep_map = {d["role"]: d["depends_on"] for d in team_plan.dependencies}
        for card in cards:
            role_deps = dep_map.get(card.role, [])
            card.dependencies = [
                role_to_task_id[d] for d in role_deps
                if d in role_to_task_id and d != card.role
            ]

        return cards

    def _generate_task_id(self, role: str, team_id: str) -> str:
        """Generate deterministic task ID from role + team."""
        raw = f"{team_id}:{role}"
        h = hashlib.md5(raw.encode()).hexdigest()[:6]
        return f"task-{role}-{h}"

    def _build_description(self, role: str, task: str,
                           team_plan, is_lead: bool) -> str:
        """Build agent-specific task description."""
        if is_lead:
            return (
                f"[LEAD] {task}\n\n"
                f"You are the lead agent for team {team_plan.team_id}.\n"
                f"Domains: {', '.join(team_plan.domains)}.\n"
                f"Coordinate with support agents and produce the final result."
            )
        return (
            f"[SUPPORT] Contribute to: {task}\n\n"
            f"Team: {team_plan.team_id}\n"
            f"Your role: {role}\n"
            f"Focus on your domain expertise. Produce output for lead review."
        )


# ── Module-level convenience ──────────────────────────────────────

def decompose(task: str, team_plan) -> list:
    """Decompose a TeamPlan into TaskCards."""
    return TaskDecomposer().decompose(task, team_plan)
