"""Multi-agent collaboration: decompose, schedule, aggregate, trace."""

from __future__ import annotations

from aos.core.orchestration.collaboration.aggregator import (
    AgentContribution,
    Aggregator,
    TeamResult,
    aggregate,
)
from aos.core.orchestration.collaboration.scheduler import (
    Scheduler,
    provider_agent_executor,
    schedule,
    stub_agent_executor,
)
from aos.core.orchestration.collaboration.task_decomposer import (
    TaskCard,
    TaskDecomposer,
    decompose,
)
from aos.core.orchestration.collaboration.trace import ExecutionTrace, TraceEvent

__all__ = [
    "AgentContribution",
    "Aggregator",
    "ExecutionTrace",
    "Scheduler",
    "TaskCard",
    "TaskDecomposer",
    "TeamResult",
    "TraceEvent",
    "aggregate",
    "decompose",
    "provider_agent_executor",
    "schedule",
    "stub_agent_executor",
]
