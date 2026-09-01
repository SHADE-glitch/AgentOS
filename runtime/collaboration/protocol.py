"""
Agent Communication Protocol — Phase 8.1

Defines the message types for inter-agent communication:
  REQUEST   — request work from an agent
  RESULT    — agent returns result
  REVIEW    — review another agent's output
  CONFLICT  — flag a conflict between outputs
  APPROVAL  — approve a result

Design:
  - Typed message dataclasses
  - Validation of required fields per message type
  - Serializable via to_dict()
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


class MessageType(str, Enum):
    REQUEST = "REQUEST"
    RESULT = "RESULT"
    REVIEW = "REVIEW"
    CONFLICT = "CONFLICT"
    APPROVAL = "APPROVAL"


@dataclass
class AgentMessage:
    """A single inter-agent message."""
    msg_type: str           # MessageType value
    team_id: str
    sender: str             # agent role name
    receiver: str           # agent role name or "team" for broadcast
    task_id: str = ""
    content: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        # Validate message type
        valid_types = {mt.value for mt in MessageType}
        if self.msg_type not in valid_types:
            raise ValueError(f"Invalid message type: {self.msg_type}. Must be one of {valid_types}")

    def to_dict(self) -> dict:
        return asdict(self)


# ── Message Constructors ──────────────────────────────────────────

def request_work(team_id: str, sender: str, receiver: str,
                 task_id: str, content: str = "") -> AgentMessage:
    """Create a REQUEST message — ask an agent to perform work."""
    return AgentMessage(
        msg_type=MessageType.REQUEST.value,
        team_id=team_id,
        sender=sender,
        receiver=receiver,
        task_id=task_id,
        content=content,
    )


def send_result(team_id: str, sender: str, receiver: str,
                task_id: str, payload: dict = None) -> AgentMessage:
    """Create a RESULT message — return completed work."""
    return AgentMessage(
        msg_type=MessageType.RESULT.value,
        team_id=team_id,
        sender=sender,
        receiver=receiver,
        task_id=task_id,
        payload=payload or {},
    )


def send_review(team_id: str, sender: str, receiver: str,
                task_id: str, content: str = "") -> AgentMessage:
    """Create a REVIEW message — review another agent's output."""
    return AgentMessage(
        msg_type=MessageType.REVIEW.value,
        team_id=team_id,
        sender=sender,
        receiver=receiver,
        task_id=task_id,
        content=content,
    )


def flag_conflict(team_id: str, sender: str, receiver: str,
                  task_id: str, content: str = "") -> AgentMessage:
    """Create a CONFLICT message — flag disagreement."""
    return AgentMessage(
        msg_type=MessageType.CONFLICT.value,
        team_id=team_id,
        sender=sender,
        receiver=receiver,
        task_id=task_id,
        content=content,
    )


def send_approval(team_id: str, sender: str, receiver: str,
                  task_id: str, content: str = "") -> AgentMessage:
    """Create an APPROVAL message — approve a result."""
    return AgentMessage(
        msg_type=MessageType.APPROVAL.value,
        team_id=team_id,
        sender=sender,
        receiver=receiver,
        task_id=task_id,
        content=content,
    )
