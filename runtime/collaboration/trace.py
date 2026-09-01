"""
Execution Trace — Phase 8.1

Records collaboration execution events:
  team_created, task_assigned, agent_started, agent_completed, result_aggregated

Design:
  - Pure data recording — no side effects beyond list append
  - Deterministic event ordering
  - Serializable via to_dict()
"""

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TraceEvent:
    """A single collaboration execution event."""
    event_type: str       # team_created | task_assigned | agent_started | agent_completed | result_aggregated
    team_id: str
    timestamp: str = ""
    task_id: str = ""
    agent_role: str = ""
    detail: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionTrace:
    """Full execution trace for a collaboration run."""
    team_id: str
    events: list = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""

    def record(self, event_type: str, task_id: str = "", agent_role: str = "",
               detail: str = "", duration_ms: float = 0.0) -> TraceEvent:
        """Record a new event and return it."""
        ts = _now_iso()
        if not self.started_at:
            self.started_at = ts
        event = TraceEvent(
            event_type=event_type,
            team_id=self.team_id,
            timestamp=ts,
            task_id=task_id,
            agent_role=agent_role,
            detail=detail,
            duration_ms=duration_ms,
        )
        self.events.append(event)
        if event_type == "result_aggregated":
            self.completed_at = ts
        return event

    def events_by_type(self, event_type: str) -> list:
        """Return all events of a given type."""
        return [e for e in self.events if e.event_type == event_type]

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }


def _now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()
