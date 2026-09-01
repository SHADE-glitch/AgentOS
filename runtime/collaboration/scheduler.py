"""
Scheduler — Phase 8.1

Executes TaskCards according to dependency order.

First version: sequential execution with dependency resolution.
Provides execution trace and supports pluggable agent execution.

Architecture:
  TaskCards → Scheduler.execute() → Completed TaskCards + ExecutionTrace
"""

import time
from typing import Callable, Optional

try:
    from .task_decomposer import TaskCard
    from .trace import ExecutionTrace
except ImportError:
    from task_decomposer import TaskCard
    from trace import ExecutionTrace


# ── Agent Executors ───────────────────────────────────────────────

def _default_agent_executor(card: TaskCard, context: dict) -> dict:
    """
    Default agent execution — produces a deterministic stub result.

    In production, replaced by create_real_executor() which calls the actual agent runtime.
    """
    return {
        "agent": card.role,
        "status": "completed",
        "summary": f"Agent {card.role} completed work on: {card.description[:80]}...",
        "output": f"Output from {card.role}",
    }


def create_real_executor(runtime_execute_fn, decision_context: dict,
                         model: str = "", provider: str = "opencode",
                         project_root: str = "",
                         timeout_seconds: int = None,
                         reliability_config = None):
    """
    Phase 7.5 — Create a real agent executor that calls the Agent OS runtime.

    This replaces the _default_agent_executor stub with actual agent invocation.
    Each TaskCard is executed by calling the runtime provider (opencode, etc.).

    Phase 7.5 improvements:
      - Added timeout_seconds: per-task timeout override for complex tasks
      - Added reliability_config: custom reliability settings for multi-agent execution

    Args:
        runtime_execute_fn: callable — runtime_adapter.execute_with_reliability
        decision_context: dict — from loop_controller (includes route_decision, skill_context)
        model: str — provider-specific model
        provider: str — runtime provider name
        project_root: str — project root for stack detection
        timeout_seconds: int or None — per-task timeout override (Phase 7.5)
        reliability_config: ReliabilityConfig or None — custom reliability settings (Phase 7.5)

    Returns:
        callable: agent_executor(card: TaskCard, context: dict) -> dict
    """
    def executor(card: TaskCard, context: dict) -> dict:
        import time as _time
        start = _time.time()

        try:
            # Build a role-specific task context for the prompt builder
            role_context = dict(decision_context)
            role_context["classification"] = dict(decision_context.get("classification", {}))
            role_context["classification"]["category"] = card.role
            role_context["classification"]["domains"] = decision_context.get("route_decision", {}).get("domains", [])

            # Execute the task card via the real runtime
            kwargs = dict(
                task_id=f"{card.team_id}-{card.task_id}",
                task_text=card.description,
                decision_context=role_context,
                model=model,
                provider=provider,
                project_root=project_root,
            )
            # Phase 7.5: Pass timeout and reliability config if provided
            if timeout_seconds is not None:
                kwargs["timeout_seconds"] = timeout_seconds
            if reliability_config is not None:
                kwargs["reliability_config"] = reliability_config

            result = runtime_execute_fn(**kwargs)

            latency_ms = int((_time.time() - start) * 1000)

            response_text = result.get("response_text", "")
            return {
                "agent": card.role,
                "status": "completed" if result.get("status") == "success" else "failed",
                "summary": response_text[:200] if response_text else "",
                "output": response_text,
                "execution_id": result.get("execution_id", ""),
                "trace_id": result.get("trace_id", ""),
                "tokens": result.get("token_usage", result.get("tokens", {})),
                "latency_ms": latency_ms,
                "reliability": result.get("reliability", {}),
            }
        except Exception as e:
            latency_ms = int((_time.time() - start) * 1000)
            return {
                "agent": card.role,
                "status": "failed",
                "summary": f"Execution failed: {e}",
                "output": "",
                "error": str(e),
                "latency_ms": latency_ms,
            }

    return executor


class Scheduler:
    """
    Executes TaskCards in dependency order.

    Supports:
      - Dependency-aware ordering (topological sort)
      - Pluggable agent executor function
      - Execution trace recording
      - Sequential execution (first version)
    """

    def __init__(self, agent_executor: Callable = None):
        self.agent_executor = agent_executor or _default_agent_executor

    def execute(self, task_cards: list, context: dict = None) -> dict:
        """
        Execute all task cards in dependency order.

        Args:
            task_cards: List of TaskCard objects
            context: Shared context dict (task, team_plan, etc.)

        Returns:
            Dict with keys: cards, trace, completed, failed
        """
        context = context or {}
        cards = {c.task_id: c for c in task_cards}
        trace = ExecutionTrace(
            team_id=task_cards[0].team_id if task_cards else ""
        )

        completed = set()
        failed = set()
        execution_order = []

        trace.record(
            event_type="team_created",
            detail=f"Team with {len(task_cards)} agents",
        )

        # Execute in dependency order (sequential)
        max_iterations = len(cards) * 2  # safety limit
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            # Find cards that are ready to run
            ready = [
                c for c in cards.values()
                if c.task_id not in completed and c.task_id not in failed
                and c.ready_to_run(completed)
            ]

            if not ready:
                break  # no more cards can run

            for card in ready:
                execution_order.append(card.task_id)
                card.status = "running"

                trace.record(
                    event_type="task_assigned",
                    task_id=card.task_id,
                    agent_role=card.role,
                    detail=f"Assigned to {card.role}",
                )

                trace.record(
                    event_type="agent_started",
                    task_id=card.task_id,
                    agent_role=card.role,
                )

                start_time = time.time()
                try:
                    result = self.agent_executor(card, context)
                    duration_ms = (time.time() - start_time) * 1000

                    card.output_data = result
                    card.status = "completed"
                    completed.add(card.task_id)

                    trace.record(
                        event_type="agent_completed",
                        task_id=card.task_id,
                        agent_role=card.role,
                        detail=f"Completed successfully",
                        duration_ms=duration_ms,
                    )
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    card.status = "failed"
                    card.output_data = {"error": str(e)}
                    failed.add(card.task_id)

                    trace.record(
                        event_type="agent_completed",
                        task_id=card.task_id,
                        agent_role=card.role,
                        detail=f"Failed: {e}",
                        duration_ms=duration_ms,
                    )

        # Check for unresolved cards (dependency cycle or missing dep)
        unresolved = [
            c.task_id for c in cards.values()
            if c.task_id not in completed and c.task_id not in failed
        ]
        for uid in unresolved:
            cards[uid].status = "failed"
            cards[uid].output_data = {"error": "Unresolved dependency"}
            failed.add(uid)

        trace.record(
            event_type="result_aggregated",
            detail=f"Completed: {len(completed)}, Failed: {len(failed)}",
        )

        return {
            "cards": list(cards.values()),
            "trace": trace,
            "completed": list(completed),
            "failed": list(failed),
            "execution_order": execution_order,
        }

    def validate_dependencies(self, task_cards: list) -> list:
        """
        Check for dependency issues without executing.

        Returns list of problems found.
        """
        card_ids = {c.task_id for c in task_cards}
        problems = []
        for card in task_cards:
            for dep in card.dependencies:
                if dep not in card_ids:
                    problems.append({
                        "task_id": card.task_id,
                        "problem": "missing_dependency",
                        "detail": f"Dependency {dep} not in task set",
                    })
            # Check for self-dependency
            if card.task_id in card.dependencies:
                problems.append({
                    "task_id": card.task_id,
                    "problem": "self_dependency",
                    "detail": "Task depends on itself",
                })
        return problems


# ── Module-level convenience ──────────────────────────────────────

def schedule(task_cards: list, context: dict = None,
             agent_executor: Callable = None) -> dict:
    """Execute task cards with the scheduler."""
    sched = Scheduler(agent_executor=agent_executor)
    return sched.execute(task_cards, context)
