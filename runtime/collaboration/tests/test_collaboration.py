#!/usr/bin/env python3
"""
Collaboration Runtime Tests — Phase 8.1

Tests:
  - TeamPlan → TaskCards conversion
  - Dependency ordering
  - Scheduler execution
  - Protocol validation
  - Aggregation correctness
  - Trace generation
  - Full pipeline integration
"""

import os
import sys
import unittest

# ── Path setup ────────────────────────────────────────────────────
_AGENT_HOME = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
_COLLAB_DIR = os.path.join(_AGENT_HOME, "runtime", "collaboration")
_ORCH_DIR = os.path.join(_AGENT_HOME, "runtime", "orchestrator")
_ROUTER_DIR = os.path.join(_AGENT_HOME, "runtime", "router")

for d in [_COLLAB_DIR, _ORCH_DIR, _ROUTER_DIR]:
    if d not in sys.path:
        sys.path.insert(0, d)

from task_decomposer import TaskCard, TaskDecomposer, decompose
from scheduler import Scheduler, schedule
from protocol import (
    MessageType, AgentMessage,
    request_work, send_result, send_review, flag_conflict, send_approval,
)
from aggregator import Aggregator, TeamResult, aggregate
from trace import TraceEvent, ExecutionTrace

# Import from orchestrator for test fixtures
from team import TeamPlan
from decision import DecisionContext


# ── Helper: Build TeamPlan fixtures ───────────────────────────────

def _make_team_plan(lead="backend-architect", supports=None, deps=None):
    """Build a TeamPlan for testing."""
    if supports is None:
        supports = ["database-engineer", "security-engineer"]
    deps = deps or []
    return TeamPlan(
        team_id="team-test0001",
        lead_agent=lead,
        support_agents=supports,
        reasoning="Test team",
        dependencies=deps,
        domains=["backend", "database", "security"],
        rules_applied=["R3: database", "R9: security"],
        pruned_roles=[],
    )


# ── Test: TaskDecomposer ─────────────────────────────────────────

class TestTaskDecomposer(unittest.TestCase):
    """Test TaskCard generation from TeamPlan."""

    def setUp(self):
        self.decomposer = TaskDecomposer()

    def test_creates_cards_for_all_roles(self):
        """One TaskCard per agent role (lead + supports)."""
        plan = _make_team_plan()
        cards = self.decomposer.decompose("Build API", plan)
        self.assertEqual(len(cards), 3)  # lead + 2 supports

    def test_lead_card_marked(self):
        """Lead agent card has is_lead=True."""
        plan = _make_team_plan()
        cards = self.decomposer.decompose("Build API", plan)
        lead_cards = [c for c in cards if c.is_lead]
        self.assertEqual(len(lead_cards), 1)
        self.assertEqual(lead_cards[0].role, "backend-architect")

    def test_support_cards_not_lead(self):
        """Support agent cards have is_lead=False."""
        plan = _make_team_plan()
        cards = self.decomposer.decompose("Build API", plan)
        support_cards = [c for c in cards if not c.is_lead]
        self.assertEqual(len(support_cards), 2)
        for c in support_cards:
            self.assertIn(c.role, ["database-engineer", "security-engineer"])

    def test_team_id_propagated(self):
        """TaskCard team_id matches TeamPlan team_id."""
        plan = _make_team_plan()
        cards = self.decomposer.decompose("Build API", plan)
        for card in cards:
            self.assertEqual(card.team_id, plan.team_id)

    def test_task_id_deterministic(self):
        """Same role+team produces same task_id."""
        plan = _make_team_plan()
        cards1 = self.decomposer.decompose("Build API", plan)
        cards2 = self.decomposer.decompose("Build API", plan)
        ids1 = {c.task_id for c in cards1}
        ids2 = {c.task_id for c in cards2}
        self.assertEqual(ids1, ids2)

    def test_dependencies_resolved(self):
        """TeamPlan dependencies converted to task_id references."""
        deps = [{"role": "database-engineer", "depends_on": ["backend-architect"]}]
        plan = _make_team_plan(deps=deps)
        cards = self.decomposer.decompose("Build API", plan)

        role_to_card = {c.role: c for c in cards}
        db_card = role_to_card["database-engineer"]
        be_card = role_to_card["backend-architect"]

        self.assertIn(be_card.task_id, db_card.dependencies)

    def test_single_agent_team(self):
        """Single-agent team produces one TaskCard."""
        plan = _make_team_plan(supports=[], deps=[])
        cards = self.decomposer.decompose("Simple task", plan)
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0].is_lead)

    def test_lead_description_contains_task(self):
        """Lead card description includes original task text."""
        plan = _make_team_plan()
        cards = self.decomposer.decompose("Build REST API", plan)
        lead = [c for c in cards if c.is_lead][0]
        self.assertIn("Build REST API", lead.description)

    def test_support_description_contains_role(self):
        """Support card description includes agent role name."""
        plan = _make_team_plan()
        cards = self.decomposer.decompose("Build REST API", plan)
        for card in cards:
            if not card.is_lead:
                self.assertIn(card.role, card.description)


# ── Test: Scheduler ──────────────────────────────────────────────

class TestScheduler(unittest.TestCase):
    """Test dependency-ordered execution."""

    def setUp(self):
        self.scheduler = Scheduler()

    def test_single_card_execution(self):
        """Single card executes and completes."""
        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work",
        )
        result = self.scheduler.execute([card])
        self.assertEqual(len(result["completed"]), 1)
        self.assertEqual(len(result["failed"]), 0)
        self.assertEqual(card.status, "completed")

    def test_dependency_order(self):
        """Cards execute in dependency order."""
        card_a = TaskCard(
            task_id="task-a", team_id="t1", role="architect",
            description="Design", dependencies=[],
        )
        card_b = TaskCard(
            task_id="task-b", team_id="t1", role="engineer",
            description="Implement", dependencies=["task-a"],
        )
        result = self.scheduler.execute([card_a, card_b])
        order = result["execution_order"]
        self.assertEqual(order.index("task-a"), 0)
        self.assertEqual(order.index("task-b"), 1)

    def test_execution_trace_generated(self):
        """Scheduler produces an ExecutionTrace."""
        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work",
        )
        result = self.scheduler.execute([card])
        self.assertIsInstance(result["trace"], ExecutionTrace)
        self.assertGreater(len(result["trace"].events), 0)

    def test_trace_records_events(self):
        """Trace contains team_created, task_assigned, agent_started, agent_completed."""
        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work",
        )
        result = self.scheduler.execute([card])
        trace = result["trace"]
        event_types = [e.event_type for e in trace.events]
        self.assertIn("team_created", event_types)
        self.assertIn("task_assigned", event_types)
        self.assertIn("agent_started", event_types)
        self.assertIn("agent_completed", event_types)
        self.assertIn("result_aggregated", event_types)

    def test_custom_executor(self):
        """Custom agent executor is called instead of default."""
        def my_executor(card, ctx):
            return {"agent": card.role, "custom": True, "ctx_key": ctx.get("key")}

        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work",
        )
        sched = Scheduler(agent_executor=my_executor)
        result = sched.execute([card], context={"key": "hello"})
        self.assertTrue(card.output_data["custom"])
        self.assertEqual(card.output_data["ctx_key"], "hello")

    def test_executor_exception_marks_failed(self):
        """Agent executor exception marks card as failed."""
        def bad_executor(card, ctx):
            raise RuntimeError("Agent crashed")

        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work",
        )
        sched = Scheduler(agent_executor=bad_executor)
        result = sched.execute([card])
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(card.status, "failed")
        self.assertIn("error", card.output_data)

    def test_validate_dependencies_missing(self):
        """validate_dependencies detects missing dependencies."""
        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work", dependencies=["task-nonexistent"],
        )
        sched = Scheduler()
        problems = sched.validate_dependencies([card])
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["problem"], "missing_dependency")

    def test_validate_dependencies_self(self):
        """validate_dependencies detects self-dependency."""
        card = TaskCard(
            task_id="task-001", team_id="t1", role="lead",
            description="Do work", dependencies=["task-001"],
        )
        sched = Scheduler()
        problems = sched.validate_dependencies([card])
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["problem"], "self_dependency")

    def test_empty_task_list(self):
        """Empty task list produces empty result."""
        result = self.scheduler.execute([])
        self.assertEqual(len(result["completed"]), 0)
        self.assertEqual(len(result["failed"]), 0)


# ── Test: Protocol ───────────────────────────────────────────────

class TestProtocol(unittest.TestCase):
    """Test agent communication protocol."""

    def test_request_work(self):
        """request_work creates a valid REQUEST message."""
        msg = request_work("t1", "lead", "engineer", "task-1", "Build API")
        self.assertEqual(msg.msg_type, MessageType.REQUEST.value)
        self.assertEqual(msg.sender, "lead")
        self.assertEqual(msg.receiver, "engineer")
        self.assertEqual(msg.task_id, "task-1")

    def test_send_result(self):
        """send_result creates a valid RESULT message."""
        msg = send_result("t1", "engineer", "lead", "task-1", {"output": "done"})
        self.assertEqual(msg.msg_type, MessageType.RESULT.value)
        self.assertEqual(msg.payload, {"output": "done"})

    def test_send_review(self):
        """send_review creates a valid REVIEW message."""
        msg = send_review("t1", "lead", "engineer", "task-1", "LGTM")
        self.assertEqual(msg.msg_type, MessageType.REVIEW.value)

    def test_flag_conflict(self):
        """flag_conflict creates a valid CONFLICT message."""
        msg = flag_conflict("t1", "engineer", "lead", "task-1", "Disagree on schema")
        self.assertEqual(msg.msg_type, MessageType.CONFLICT.value)

    def test_send_approval(self):
        """send_approval creates a valid APPROVAL message."""
        msg = send_approval("t1", "lead", "engineer", "task-1", "Approved")
        self.assertEqual(msg.msg_type, MessageType.APPROVAL.value)

    def test_invalid_message_type(self):
        """Invalid message type raises ValueError."""
        with self.assertRaises(ValueError):
            AgentMessage(
                msg_type="INVALID",
                team_id="t1",
                sender="a",
                receiver="b",
            )

    def test_timestamp_auto_set(self):
        """Message timestamp is auto-set if not provided."""
        msg = request_work("t1", "a", "b", "task-1")
        self.assertNotEqual(msg.timestamp, "")

    def test_message_serialization(self):
        """AgentMessage.to_dict() returns a dict."""
        msg = request_work("t1", "a", "b", "task-1", "content")
        d = msg.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["msg_type"], "REQUEST")


# ── Test: Aggregator ─────────────────────────────────────────────

class TestAggregator(unittest.TestCase):
    """Test result aggregation."""

    def setUp(self):
        self.aggregator = Aggregator()

    def test_all_completed_success(self):
        """All cards completed → status success."""
        cards = [
            TaskCard("t1", "t1", "lead", "Design", status="completed",
                     output_data={"result": "design"}, is_lead=True),
            TaskCard("t2", "t1", "engineer", "Code", status="completed",
                     output_data={"result": "code"}),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.completed_count, 2)
        self.assertEqual(result.failed_count, 0)

    def test_partial_failure(self):
        """Some cards failed → status partial."""
        cards = [
            TaskCard("t1", "t1", "lead", "Design", status="completed",
                     output_data={"result": "design"}, is_lead=True),
            TaskCard("t2", "t1", "engineer", "Code", status="failed",
                     output_data={"error": "crash"}),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.completed_count, 1)
        self.assertEqual(result.failed_count, 1)

    def test_all_failed(self):
        """All cards failed → status failed."""
        cards = [
            TaskCard("t1", "t1", "lead", "Design", status="failed",
                     output_data={"error": "crash"}, is_lead=True),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertEqual(result.status, "failed")

    def test_lead_output_primary(self):
        """Lead agent output is in lead_output field."""
        cards = [
            TaskCard("t1", "t1", "lead", "Design", status="completed",
                     output_data={"result": "design"}, is_lead=True),
            TaskCard("t2", "t1", "engineer", "Code", status="completed",
                     output_data={"result": "code"}),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertEqual(result.lead_output, {"result": "design"})

    def test_contributions_collected(self):
        """All completed agents appear in contributions."""
        cards = [
            TaskCard("t1", "t1", "lead", "Design", status="completed",
                     output_data={"result": "design"}, is_lead=True),
            TaskCard("t2", "t1", "engineer", "Code", status="completed",
                     output_data={"result": "code"}),
            TaskCard("t3", "t1", "reviewer", "Review", status="completed",
                     output_data={"result": "review"}),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertEqual(len(result.contributions), 3)
        roles = [c["role"] for c in result.contributions]
        self.assertIn("lead", roles)
        self.assertIn("engineer", roles)
        self.assertIn("reviewer", roles)

    def test_conflict_detection(self):
        """Conflicting support outputs are flagged."""
        cards = [
            TaskCard("t1", "t1", "a", "Work A", status="completed",
                     output_data={"conflicts_with": "b",
                                   "conflict_detail": "Schema mismatch"}),
            TaskCard("t2", "t1", "b", "Work B", status="completed",
                     output_data={}),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertEqual(len(result.conflicts), 1)
        self.assertIn("a", result.conflicts[0]["agents"])

    def test_empty_cards(self):
        """Empty card list produces failed result."""
        result = self.aggregator.aggregate([])
        self.assertEqual(result.status, "failed")

    def test_summary_generated(self):
        """Summary is a non-empty string."""
        cards = [
            TaskCard("t1", "t1", "lead", "Design", status="completed",
                     output_data={}, is_lead=True),
        ]
        result = self.aggregator.aggregate(cards)
        self.assertIsInstance(result.summary, str)
        self.assertGreater(len(result.summary), 0)


# ── Test: ExecutionTrace ─────────────────────────────────────────

class TestExecutionTrace(unittest.TestCase):
    """Test trace recording."""

    def test_record_event(self):
        """record() adds an event to the trace."""
        trace = ExecutionTrace(team_id="t1")
        event = trace.record("team_created", detail="Team formed")
        self.assertEqual(len(trace.events), 1)
        self.assertEqual(event.event_type, "team_created")
        self.assertEqual(event.team_id, "t1")

    def test_multiple_events(self):
        """Multiple events are recorded in order."""
        trace = ExecutionTrace(team_id="t1")
        trace.record("team_created")
        trace.record("task_assigned", task_id="t1", agent_role="lead")
        trace.record("agent_started", task_id="t1", agent_role="lead")
        trace.record("agent_completed", task_id="t1", agent_role="lead")
        self.assertEqual(len(trace.events), 4)

    def test_events_by_type(self):
        """events_by_type filters correctly."""
        trace = ExecutionTrace(team_id="t1")
        trace.record("team_created")
        trace.record("task_assigned", task_id="t1")
        trace.record("task_assigned", task_id="t2")
        assigned = trace.events_by_type("task_assigned")
        self.assertEqual(len(assigned), 2)

    def test_started_at_set(self):
        """started_at is set on first event."""
        trace = ExecutionTrace(team_id="t1")
        self.assertEqual(trace.started_at, "")
        trace.record("team_created")
        self.assertNotEqual(trace.started_at, "")

    def test_completed_at_set(self):
        """completed_at is set on result_aggregated event."""
        trace = ExecutionTrace(team_id="t1")
        trace.record("team_created")
        trace.record("result_aggregated")
        self.assertNotEqual(trace.completed_at, "")

    def test_serialization(self):
        """to_dict() returns a valid dict."""
        trace = ExecutionTrace(team_id="t1")
        trace.record("team_created")
        d = trace.to_dict()
        self.assertEqual(d["team_id"], "t1")
        self.assertEqual(d["event_count"], 1)
        self.assertEqual(len(d["events"]), 1)


# ── Test: Full Pipeline Integration ──────────────────────────────

class TestFullPipeline(unittest.TestCase):
    """Integration test: TeamPlan → TaskCards → Scheduler → Aggregator."""

    def test_end_to_end(self):
        """Full pipeline from TeamPlan to TeamResult."""
        plan = _make_team_plan(
            supports=["database-engineer"],
            deps=[{"role": "database-engineer", "depends_on": ["backend-architect"]}],
        )

        # Step 1: Decompose
        cards = decompose("Design a scalable API", plan)
        self.assertEqual(len(cards), 2)

        # Step 2: Schedule
        result = schedule(cards)
        self.assertEqual(len(result["completed"]), 2)
        self.assertEqual(len(result["failed"]), 0)

        # Step 3: Aggregate
        team_result = aggregate(result["cards"], result["trace"])
        self.assertEqual(team_result.status, "success")
        self.assertEqual(team_result.completed_count, 2)
        self.assertGreater(len(team_result.contributions), 0)

    def test_pipeline_with_failure(self):
        """Pipeline handles agent failure gracefully."""
        def failing_executor(card, ctx):
            if card.role == "database-engineer":
                raise RuntimeError("DB connection failed")
            return {"agent": card.role, "status": "done"}

        plan = _make_team_plan(supports=["database-engineer"])
        cards = decompose("Design API", plan)
        result = schedule(cards, agent_executor=failing_executor)
        team_result = aggregate(result["cards"], result["trace"])
        self.assertEqual(team_result.status, "partial")
        self.assertEqual(team_result.failed_count, 1)

    def test_pipeline_with_dependencies(self):
        """Pipeline respects dependency ordering."""
        deps = [{"role": "database-engineer", "depends_on": ["backend-architect"]}]
        plan = _make_team_plan(
            supports=["database-engineer"],
            deps=deps,
        )
        cards = decompose("Build system", plan)
        result = schedule(cards)
        order = result["execution_order"]
        # Lead (backend-architect) must come before database-engineer
        be_id = [c.task_id for c in cards if c.role == "backend-architect"][0]
        db_id = [c.task_id for c in cards if c.role == "database-engineer"][0]
        self.assertLess(order.index(be_id), order.index(db_id))


# ── Test: Regression — Phase 7 modules still work ───────────────

class TestRegressionRouter(unittest.TestCase):
    """Verify Phase 7.1 Router still works."""

    @classmethod
    def setUpClass(cls):
        from router import Router
        cls.router = Router()
        cls.router.load_rules()

    def test_router_classifies(self):
        """Router can classify a task."""
        result = self.router.classify("Build a REST API for user management")
        self.assertIsNotNone(result)
        self.assertIn("backend", result.domains)

    def test_router_routes(self):
        """Router can produce a DecisionContext."""
        d = self.router.route("Build a REST API for user management")
        self.assertIsNotNone(d.lead_skill)
        self.assertEqual(d.intent, "coding")


class TestRegressionOrchestrator(unittest.TestCase):
    """Verify Phase 7.3 Orchestrator still works."""

    @classmethod
    def setUpClass(cls):
        from router import Router
        from orchestrator import Orchestrator
        cls.router = Router()
        cls.router.load_rules()
        cls.orch = Orchestrator()
        cls.orch.load_rules()

    def test_form_team(self):
        """Orchestrator can form a team."""
        d = self.router.route("Design a scalable distributed system")
        team = self.orch.form_team(d.task_text, d)
        self.assertIsNotNone(team.team_id)
        self.assertIsNotNone(team.lead_agent)


# ── Runner ───────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
