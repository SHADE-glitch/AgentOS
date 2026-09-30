"""Dependency-ordered task card execution.

Ported from ``runtime/collaboration/scheduler.py``. Sequential execution with
topological ordering and an execution trace; the agent executor is pluggable
so tests use a deterministic stub and the loop can supply a real provider.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from aos.core.orchestration.collaboration.task_decomposer import TaskCard
from aos.core.orchestration.collaboration.trace import ExecutionTrace

AgentExecutor = Callable[[TaskCard, dict[str, Any]], dict[str, Any]]


def stub_agent_executor(card: TaskCard, context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic executor used by tests and dry runs."""
    return {
        "agent": card.role,
        "status": "completed",
        "summary": f"{card.role} completed: {card.description[:80]}",
        "output": f"Output from {card.role}",
    }


def provider_agent_executor(provider: Any, *, model: str = "", cwd: str = "") -> AgentExecutor:
    """Build an executor that runs each card through a :class:`Provider`."""

    def executor(card: TaskCard, context: dict[str, Any]) -> dict[str, Any]:
        result = provider.invoke(prompt=card.description, model=model, cwd=cwd)
        return {
            "agent": card.role,
            "status": "completed" if result.ok else "failed",
            "summary": (result.response_text or "")[:200],
            "output": result.response_text,
            "error": result.error,
            "tokens": dict(result.tokens),
            "latency_ms": result.latency_ms,
        }

    return executor


class Scheduler:
    def __init__(self, agent_executor: AgentExecutor | None = None):
        self.agent_executor: AgentExecutor = agent_executor or stub_agent_executor

    def execute(self, task_cards: list[TaskCard], context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        cards = {card.task_id: card for card in task_cards}
        trace = ExecutionTrace(team_id=task_cards[0].team_id if task_cards else "")

        completed: set[str] = set()
        failed: set[str] = set()
        execution_order: list[str] = []

        trace.record("team_created", detail=f"team with {len(task_cards)} agent(s)")

        # Bounded loop: each pass runs at least one card, so len(cards) passes suffice.
        for _ in range(len(cards) + 1):
            ready = [
                card
                for card in cards.values()
                if card.task_id not in completed
                and card.task_id not in failed
                and card.ready_to_run(completed)
            ]
            if not ready:
                break

            for card in ready:
                execution_order.append(card.task_id)
                card.status = "running"
                trace.record("task_assigned", task_id=card.task_id, agent_role=card.role)
                trace.record("agent_started", task_id=card.task_id, agent_role=card.role)

                started = time.time()
                try:
                    result = self.agent_executor(card, context)
                    duration_ms = (time.time() - started) * 1000
                    card.output_data = result
                    if result.get("status") == "failed":
                        card.status = "failed"
                        failed.add(card.task_id)
                        trace.record(
                            "agent_completed",
                            task_id=card.task_id,
                            agent_role=card.role,
                            detail="failed",
                            duration_ms=duration_ms,
                        )
                    else:
                        card.status = "completed"
                        completed.add(card.task_id)
                        trace.record(
                            "agent_completed",
                            task_id=card.task_id,
                            agent_role=card.role,
                            detail="completed",
                            duration_ms=duration_ms,
                        )
                except Exception as exc:  # an agent crashing must not kill the team
                    duration_ms = (time.time() - started) * 1000
                    card.status = "failed"
                    card.output_data = {"error": str(exc)}
                    failed.add(card.task_id)
                    trace.record(
                        "agent_completed",
                        task_id=card.task_id,
                        agent_role=card.role,
                        detail=f"failed: {exc}",
                        duration_ms=duration_ms,
                    )

        # Anything still pending has an unsatisfiable dependency.
        for card in cards.values():
            if card.task_id not in completed and card.task_id not in failed:
                card.status = "failed"
                card.output_data = {"error": "unresolved dependency"}
                failed.add(card.task_id)

        trace.record(
            "result_aggregated",
            detail=f"completed: {len(completed)}, failed: {len(failed)}",
        )
        return {
            "cards": list(cards.values()),
            "trace": trace,
            "completed": sorted(completed),
            "failed": sorted(failed),
            "execution_order": execution_order,
        }

    def validate_dependencies(self, task_cards: list[TaskCard]) -> list[dict[str, Any]]:
        card_ids = {card.task_id for card in task_cards}
        problems = []
        for card in task_cards:
            for dependency in card.dependencies:
                if dependency not in card_ids:
                    problems.append(
                        {
                            "task_id": card.task_id,
                            "problem": "missing_dependency",
                            "detail": f"dependency {dependency} not in task set",
                        }
                    )
            if card.task_id in card.dependencies:
                problems.append(
                    {"task_id": card.task_id, "problem": "self_dependency", "detail": "task depends on itself"}
                )
        return problems


def schedule(
    task_cards: list[TaskCard],
    context: dict[str, Any] | None = None,
    agent_executor: AgentExecutor | None = None,
) -> dict[str, Any]:
    return Scheduler(agent_executor=agent_executor).execute(task_cards, context)
