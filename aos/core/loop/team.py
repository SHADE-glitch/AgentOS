"""Executor / team metadata for a loop.

Phase 5 only needs to record *whether* a loop is single- or multi-agent and
which roles are in play. The real team formation (decomposition, scheduling,
aggregation) is ported in Phase 6 and plugs into :func:`plan_executor`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class ExecutorPlan:
    """How a loop's work will be carried out."""

    is_multi_agent: bool
    lead_role: str
    support_roles: list[str] = field(default_factory=list)
    team_id: str = ""
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "multi-agent" if self.is_multi_agent else "single-agent",
            "is_multi_agent": self.is_multi_agent,
            "lead_role": self.lead_role,
            "support_roles": list(self.support_roles),
            "team_id": self.team_id,
            "rationale": self.rationale,
        }


def plan_executor(
    *,
    lead_role: str,
    support_roles: list[str],
    domains: list[str],
    difficulty: str = "medium",
) -> ExecutorPlan:
    """Decide single vs multi agent.

    A team is formed only when the task genuinely spans more than one domain,
    or is hard *and* has a support role to hand work to. Otherwise the loop
    degrades cleanly to a single agent.
    """
    supports = [role for role in support_roles if role and role != lead_role]
    multi = bool(supports) and (len(set(domains)) >= 2 or difficulty == "hard")
    if multi:
        rationale = f"spans {len(set(domains))} domain(s) with difficulty={difficulty}"
        team_id = f"TEAM-{uuid.uuid4().hex[:6].upper()}"
    else:
        rationale = "single domain and no hard escalation"
        team_id = ""
    return ExecutorPlan(
        is_multi_agent=multi,
        lead_role=lead_role,
        support_roles=supports,
        team_id=team_id,
        rationale=rationale,
    )
