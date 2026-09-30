"""Collaboration execution trace.

Ported from ``runtime/collaboration/trace.py``. Pure data recording: no side
effects beyond appending to a list, deterministic ordering, serialisable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

EVENT_TYPES = (
    "team_created",
    "task_assigned",
    "agent_started",
    "agent_completed",
    "result_aggregated",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    event_type: str
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
    team_id: str
    events: list[TraceEvent] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""

    def record(
        self,
        event_type: str,
        *,
        task_id: str = "",
        agent_role: str = "",
        detail: str = "",
        duration_ms: float = 0.0,
    ) -> TraceEvent:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown trace event {event_type!r}")
        timestamp = _now_iso()
        if not self.started_at:
            self.started_at = timestamp
        event = TraceEvent(
            event_type=event_type,
            team_id=self.team_id,
            timestamp=timestamp,
            task_id=task_id,
            agent_role=agent_role,
            detail=detail,
            duration_ms=duration_ms,
        )
        self.events.append(event)
        if event_type == "result_aggregated":
            self.completed_at = timestamp
        return event

    def events_by_type(self, event_type: str) -> list[TraceEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }
