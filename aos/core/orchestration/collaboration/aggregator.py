"""Aggregate agent outputs into a team result.

Ported from ``runtime/collaboration/aggregator.py``. The lead has final
authority; support outputs are collected as contributions; explicit
disagreements are surfaced as conflicts rather than silently resolved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from aos.core.orchestration.collaboration.task_decomposer import TaskCard
from aos.core.orchestration.collaboration.trace import ExecutionTrace


@dataclass
class AgentContribution:
    role: str
    task_id: str
    output: dict[str, Any] = field(default_factory=dict)
    is_lead: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TeamResult:
    team_id: str
    status: str = "success"  # success | partial | failed
    lead_output: dict[str, Any] = field(default_factory=dict)
    contributions: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    agent_count: int = 0
    completed_count: int = 0
    failed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Aggregator:
    def aggregate(
        self, task_cards: list[TaskCard], trace: Optional[ExecutionTrace] = None
    ) -> TeamResult:
        team_id = task_cards[0].team_id if task_cards else ""
        completed = [c for c in task_cards if c.status == "completed"]
        failed = [c for c in task_cards if c.status == "failed"]
        lead_cards = [c for c in completed if c.is_lead]
        support_cards = [c for c in completed if not c.is_lead]

        contributions = [
            AgentContribution(
                role=card.role, task_id=card.task_id, output=card.output_data, is_lead=card.is_lead
            ).to_dict()
            for card in completed
        ]
        conflicts = self._detect_conflicts(support_cards)

        if not completed:
            status = "failed"
        elif failed:
            status = "partial"
        else:
            status = "success"

        result = TeamResult(
            team_id=team_id,
            status=status,
            lead_output=lead_cards[0].output_data if lead_cards else {},
            contributions=contributions,
            conflicts=conflicts,
            summary=self._summarize(lead_cards, support_cards, failed, conflicts),
            agent_count=len(task_cards),
            completed_count=len(completed),
            failed_count=len(failed),
        )
        if trace:
            trace.record(
                "result_aggregated",
                detail=f"status: {status}, completed: {len(completed)}, failed: {len(failed)}",
            )
        return result

    def _detect_conflicts(self, support_cards: list[TaskCard]) -> list[dict[str, Any]]:
        conflicts = []
        outputs = [(card.role, card.output_data) for card in support_cards]
        for i, (role_a, out_a) in enumerate(outputs):
            for role_b, out_b in outputs[i + 1 :]:
                if out_a.get("conflicts_with") == role_b:
                    conflicts.append(
                        {"type": "explicit", "agents": [role_a, role_b], "detail": out_a.get("conflict_detail", "")}
                    )
                elif out_b.get("conflicts_with") == role_a:
                    conflicts.append(
                        {"type": "explicit", "agents": [role_b, role_a], "detail": out_b.get("conflict_detail", "")}
                    )
        return conflicts

    def _summarize(self, lead_cards, support_cards, failed, conflicts) -> str:
        parts = []
        if lead_cards:
            parts.append(f"lead ({lead_cards[0].role}) completed primary work")
        if support_cards:
            parts.append(f"support ({', '.join(c.role for c in support_cards)}) contributed")
        if failed:
            parts.append(f"{len(failed)} agent(s) failed")
        if conflicts:
            parts.append(f"{len(conflicts)} conflict(s) detected")
        return ". ".join(parts) if parts else "no results"


def aggregate(task_cards: list[TaskCard], trace: Optional[ExecutionTrace] = None) -> TeamResult:
    return Aggregator().aggregate(task_cards, trace)
