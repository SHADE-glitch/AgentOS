"""
Collaboration Runtime — Phase 8.1

Multi-agent execution layer after Orchestrator TeamPlan.

Architecture:
  TeamPlan → TaskDecomposer → TaskCards → Scheduler → Aggregator → TeamResult

Modules:
  - task_decomposer: Convert TeamPlan into executable TaskCards
  - scheduler: Execute TaskCards in dependency order
  - protocol: Agent communication message types
  - aggregator: Collect and merge agent outputs
  - trace: Execution event recording
"""

try:
    from .task_decomposer import TaskCard, TaskDecomposer, decompose
    from .scheduler import Scheduler, schedule, create_real_executor
    from .protocol import (
        MessageType, AgentMessage,
        request_work, send_result, send_review, flag_conflict, send_approval,
    )
    from .aggregator import Aggregator, TeamResult, aggregate
    from .trace import TraceEvent, ExecutionTrace
except ImportError:
    from task_decomposer import TaskCard, TaskDecomposer, decompose
    from scheduler import Scheduler, schedule, create_real_executor
    from protocol import (
        MessageType, AgentMessage,
        request_work, send_result, send_review, flag_conflict, send_approval,
    )
    from aggregator import Aggregator, TeamResult, aggregate
    from trace import TraceEvent, ExecutionTrace

__all__ = [
    "TaskCard", "TaskDecomposer", "decompose",
    "Scheduler", "schedule", "create_real_executor",
    "MessageType", "AgentMessage",
    "request_work", "send_result", "send_review", "flag_conflict", "send_approval",
    "Aggregator", "TeamResult", "aggregate",
    "TraceEvent", "ExecutionTrace",
]
