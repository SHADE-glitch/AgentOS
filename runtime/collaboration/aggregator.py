"""
Aggregator — Phase 8.1

Collects agent outputs and merges results into a final team result.

Rules:
  - Lead agent output has final authority
  - Support agent outputs are collected as contributions
  - Conflicts between agents are flagged for review
  - Final result includes all agent outputs plus merged summary

Architecture:
  Completed TaskCards → Aggregator.aggregate() → TeamResult
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class AgentContribution:
    """A single agent's contribution to the team result."""
    role: str
    task_id: str
    output: dict = field(default_factory=dict)
    is_lead: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TeamResult:
    """Aggregated result from a multi-agent collaboration."""
    team_id: str
    status: str = "success"          # success | partial | failed
    lead_output: dict = field(default_factory=dict)
    contributions: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    summary: str = ""
    agent_count: int = 0
    completed_count: int = 0
    failed_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class Aggregator:
    """
    Aggregates completed TaskCards into a TeamResult.

    Logic:
      1. Collect all completed agent outputs
      2. Separate lead vs support contributions
      3. Detect conflicts (support outputs contradicting each other)
      4. Merge into final result (lead has authority)
    """

    def aggregate(self, task_cards: list, trace=None) -> TeamResult:
        """
        Aggregate completed task cards into a team result.

        Args:
            task_cards: List of TaskCard objects (from scheduler output)
            trace: Optional ExecutionTrace to record aggregation event

        Returns:
            TeamResult with merged outputs
        """
        team_id = task_cards[0].team_id if task_cards else ""
        completed = [c for c in task_cards if c.status == "completed"]
        failed = [c for c in task_cards if c.status == "failed"]

        # Separate lead and support
        lead_cards = [c for c in completed if c.is_lead]
        support_cards = [c for c in completed if not c.is_lead]

        # Build contributions
        contributions = []
        for card in completed:
            contributions.append(AgentContribution(
                role=card.role,
                task_id=card.task_id,
                output=card.output_data,
                is_lead=card.is_lead,
            ))

        # Lead output (primary)
        lead_output = lead_cards[0].output_data if lead_cards else {}

        # Detect conflicts between support agents
        conflicts = self._detect_conflicts(support_cards)

        # Determine status
        if not completed:
            status = "failed"
        elif failed:
            status = "partial"
        else:
            status = "success"

        # Build summary
        summary = self._build_summary(
            lead_cards, support_cards, failed, conflicts
        )

        result = TeamResult(
            team_id=team_id,
            status=status,
            lead_output=lead_output,
            contributions=[c.to_dict() for c in contributions],
            conflicts=conflicts,
            summary=summary,
            agent_count=len(task_cards),
            completed_count=len(completed),
            failed_count=len(failed),
        )

        if trace:
            trace.record(
                event_type="result_aggregated",
                detail=f"Status: {status}, Agents: {len(task_cards)}, "
                       f"Completed: {len(completed)}, Failed: {len(failed)}",
            )

        return result

    def _detect_conflicts(self, support_cards: list) -> list:
        """
        Detect conflicts between support agent outputs.

        Simple heuristic: if two support agents produce outputs with
        different 'status' fields, flag it as a potential conflict.
        """
        conflicts = []
        if len(support_cards) < 2:
            return conflicts

        outputs = [(c.role, c.output_data) for c in support_cards]
        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                role_a, out_a = outputs[i]
                role_b, out_b = outputs[j]
                # Check for explicit conflict markers
                if out_a.get("conflicts_with") == role_b:
                    conflicts.append({
                        "type": "explicit",
                        "agents": [role_a, role_b],
                        "detail": out_a.get("conflict_detail", ""),
                    })
                elif out_b.get("conflicts_with") == role_a:
                    conflicts.append({
                        "type": "explicit",
                        "agents": [role_b, role_a],
                        "detail": out_b.get("conflict_detail", ""),
                    })
        return conflicts

    def _build_summary(self, lead_cards, support_cards, failed, conflicts) -> str:
        """Build human-readable summary of team result."""
        parts = []
        if lead_cards:
            lead = lead_cards[0].role
            parts.append(f"Lead agent ({lead}) completed primary work")
        if support_cards:
            roles = [c.role for c in support_cards]
            parts.append(f"Support agents ({', '.join(roles)}) contributed")
        if failed:
            parts.append(f"{len(failed)} agent(s) failed")
        if conflicts:
            parts.append(f"{len(conflicts)} conflict(s) detected")
        return ". ".join(parts) if parts else "No results"


# ── Module-level convenience ──────────────────────────────────────

def aggregate(task_cards: list, trace=None) -> TeamResult:
    """Aggregate completed task cards into a team result."""
    return Aggregator().aggregate(task_cards, trace)
