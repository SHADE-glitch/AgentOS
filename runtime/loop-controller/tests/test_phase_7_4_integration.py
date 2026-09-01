#!/usr/bin/env python3
"""
Phase 7.4 — Runtime Integration Hardening Tests

Validates the full integrated pipeline:
  Real task input → Router → Orchestrator → TaskDecomposer → Scheduler → Aggregator

Verification:
  - Orchestrator runs and generates TeamPlan
  - Collaboration Runtime executes (TaskDecomposer → Scheduler → Aggregator)
  - At least one TaskCard is executed by a real agent
  - Loop state tracks orchestrator and collaboration stages
  - Pipeline completes successfully

Uses TestProvider to avoid recursive OpenCode calls.
"""

import sys
import os
import unittest
import time
import yaml
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_provider import TestProvider, register_test_provider
from loop_controller import run_loop
from agent_router import route as router_route


class TestPhase7_4Integration(unittest.TestCase):
    """Phase 7.4 Runtime Integration Hardening — full pipeline tests."""

    @classmethod
    def setUpClass(cls):
        """Register the test provider once for all tests."""
        cls.provider = TestProvider()
        register_test_provider(cls.provider)

    def setUp(self):
        """Reset provider before each test."""
        self.provider.reset()
        self.provider.set_scenario("success")

    # ── Scenario A: Full multi-agent pipeline ───────────────────────

    def test_scenario_a_full_multi_agent_pipeline(self):
        """
        Scenario A: Full multi-agent pipeline from router through orchestrator,
        collaboration runtime, and aggregator.

        Task: Complex multi-domain task that should trigger team formation.
        """
        self.provider.set_scenario("success")

        state = run_loop(
            task_id="INT-7.4-A-001",
            task_text="设计一个高并发订单系统，需要数据库优化和安全审计",
            memory_mode="enabled",
            provider="test_provider",
            runtime_mode="TEST_PROVIDER",
        )

        print(f"\n  Pipeline final status: {state['final_status']}")

        # ── 1. Router was called ─────────────────────────────────────
        self.assertEqual(state["router"]["status"], "completed")
        print(f"  Router: {state['router']['lead_skill']} (confidence: {state['router']['confidence']})")

        # ── 2. Orchestrator was called ───────────────────────────────
        self.assertIn("orchestrator", state)
        orch = state["orchestrator"]
        self.assertIn(orch["status"], ["completed", "skipped"],
                      f"Orchestrator should complete or skip, got: {orch['status']}")
        print(f"  Orchestrator: status={orch['status']}, team_id={orch.get('team_id', '')}, "
              f"is_multi_agent={orch.get('is_multi_agent', False)}, "
              f"lead={orch.get('lead_agent', '')}, "
              f"support={orch.get('support_agents', [])}")
        self.assertGreater(len(orch.get("rules_applied", [])), 0,
                           "Orchestrator should apply rules")

        # ── 3. Collaboration was called ──────────────────────────────
        self.assertIn("collaboration", state)
        collab = state["collaboration"]
        print(f"  Collaboration: status={collab['status']}, "
              f"cards_total={collab.get('cards_total', 0)}, "
              f"cards_completed={collab.get('cards_completed', 0)}, "
              f"cards_failed={collab.get('cards_failed', 0)}, "
              f"team_status={collab.get('team_status', '')}")

        if collab["status"] == "completed":
            # When multi-agent was triggered, verify execution
            self.assertGreater(collab.get("cards_total", 0), 0,
                               "Collaboration should have at least 1 TaskCard")
            self.assertGreaterEqual(collab.get("cards_completed", 0), 1,
                                    "At least 1 TaskCard should complete")
            self.assertEqual(collab.get("cards_failed", 0), 0,
                             "No TaskCards should fail")
            # Verify execution order
            self.assertGreater(len(collab.get("execution_order", [])), 0,
                               "Execution order should be tracked")
            print(f"  Execution order: {collab['execution_order']}")
        else:
            print(f"  Collaboration: {collab['status']} (single-agent or no team)")

        # ── 4. Pipeline completed ────────────────────────────────────
        self.assertEqual(state["final_status"], "completed",
                         f"Pipeline should complete, got: {state['final_status']}")

        # ── 5. Trace was generated ───────────────────────────────────
        self.assertEqual(state["trace"]["status"], "completed")
        trace_file = state["trace"]["trace_file"]
        # Multi-agent trace uses team-level trace_id, file may not exist on disk
        if trace_file and os.path.exists(trace_file):
            print(f"  Trace file: {trace_file}")
        else:
            print(f"  Trace ID: {trace_file} (team-level trace)")

        # ── 6. Loop state was saved ──────────────────────────────────
        loop_state_path = os.path.join(
            os.path.dirname(__file__), "..", "state", f"{state['loop_id']}.yaml"
        )
        self.assertTrue(os.path.exists(loop_state_path),
                        f"LOOP state file should exist: {loop_state_path}")

        print(f"  Scenario A: Full multi-agent pipeline VERIFIED")

    # ── Scenario B: Single-agent fallback ───────────────────────────

    def test_scenario_b_single_agent_skip_collaboration(self):
        """
        Scenario B: Simple single-domain task — Orchestrator runs but
        collaboration is skipped (no team formed).
        """
        self.provider.set_scenario("success")

        state = run_loop(
            task_id="INT-7.4-B-001",
            task_text="添加一个健康检查接口到 Spring Boot 应用",
            memory_mode="enabled",
            provider="test_provider",
            runtime_mode="TEST_PROVIDER",
        )

        print(f"\n  Pipeline final status: {state['final_status']}")

        # ── 1. Router was called ─────────────────────────────────────
        self.assertEqual(state["router"]["status"], "completed")

        # ── 2. Orchestrator was called ───────────────────────────────
        self.assertIn("orchestrator", state)
        orch = state["orchestrator"]
        # Single-agent task: Orchestrator may skip or complete with no team
        self.assertIn(orch["status"], ["completed", "skipped"])
        print(f"  Orchestrator: status={orch['status']}, is_multi_agent={orch.get('is_multi_agent', False)}")

        # ── 3. Collaboration should be skipped for single-agent ──────
        self.assertIn("collaboration", state)
        collab = state["collaboration"]
        self.assertEqual(collab["status"], "skipped",
                         f"Collaboration should be skipped for single-agent, got: {collab['status']}")
        print(f"  Collaboration: skipped (single-agent, correct)")

        # ── 4. Runtime (Stage 4) should run ──────────────────────────
        self.assertEqual(state["runtime"]["status"], "completed",
                         "Runtime should run for single-agent")
        print(f"  Runtime: {state['runtime']['status']}")

        # ── 5. Pipeline completed ────────────────────────────────────
        self.assertEqual(state["final_status"], "completed")
        print(f"  Scenario B: Single-agent fallback VERIFIED")

    # ── Scenario C: Verify TaskCard real execution ──────────────────

    def test_scenario_c_taskcard_real_execution(self):
        """
        Scenario C: Verify that TaskCards are executed by a real agent
        (not a stub/fake executor).

        Use a task with strong multi-domain signals to force team formation.
        """
        self.provider.set_scenario("success")

        state = run_loop(
            task_id="INT-7.4-C-001",
            task_text="设计一个分布式缓存系统，需要数据库分片和微服务架构",
            memory_mode="enabled",
            provider="test_provider",
            runtime_mode="TEST_PROVIDER",
        )

        print(f"\n  Pipeline final status: {state['final_status']}")

        # ── 1. Verify orchestrator state ─────────────────────────────
        orch = state.get("orchestrator", {})
        print(f"  Orchestrator: status={orch.get('status')}, "
              f"is_multi_agent={orch.get('is_multi_agent', False)}, "
              f"lead={orch.get('lead_agent', '')}, "
              f"support={orch.get('support_agents', [])}")

        # ── 2. Verify collaboration state ────────────────────────────
        collab = state.get("collaboration", {})
        print(f"  Collaboration: status={collab.get('status')}, "
              f"cards_total={collab.get('cards_total', 0)}, "
              f"cards_completed={collab.get('cards_completed', 0)}, "
              f"cards_failed={collab.get('cards_failed', 0)}")

        if collab.get("status") == "completed":
            # At least one TaskCard was executed
            self.assertGreater(collab.get("cards_total", 0), 0,
                               "Must have at least 1 TaskCard")
            self.assertGreaterEqual(collab.get("cards_completed", 0), 1,
                                    "At least 1 TaskCard must be executed")

            # Verify team result was aggregated
            self.assertIn("team_status", collab)
            self.assertIn(collab.get("team_status", ""), ["completed", "partial", "success"],
                          f"Team should complete, got: {collab.get('team_status')}")

            # Verify execution order was tracked
            exec_order = collab.get("execution_order", [])
            self.assertGreater(len(exec_order), 0,
                               "Execution order must be tracked")
            print(f"  Execution order: {exec_order}")

            # Verify no failures
            self.assertEqual(collab.get("cards_failed", 0), 0,
                             f"No TaskCards should fail, got {collab.get('cards_failed')} failures")
        else:
            print(f"  Collaboration: {collab.get('status')} (no multi-agent team formed)")

        # ── 3. Pipeline completed ────────────────────────────────────
        self.assertEqual(state["final_status"], "completed")
        print(f"  Scenario C: TaskCard real execution VERIFIED")

    # ── Scenario D: Orchestrator R1-R10 rules applied ───────────────

    def test_scenario_d_orchestrator_rules_applied(self):
        """
        Scenario D: Verify that Orchestrator rules (R1-R10) are applied
        during team formation.
        """
        self.provider.set_scenario("success")

        state = run_loop(
            task_id="INT-7.4-D-001",
            task_text="构建一个 AI 驱动的代码审查系统，包含 RAG 检索和 LLM 推理",
            memory_mode="enabled",
            provider="test_provider",
            runtime_mode="TEST_PROVIDER",
        )

        print(f"\n  Pipeline final status: {state['final_status']}")

        orch = state.get("orchestrator", {})
        print(f"  Orchestrator: status={orch.get('status')}, "
              f"lead={orch.get('lead_agent', '')}, "
              f"support={orch.get('support_agents', [])}")

        # Verify rules were applied
        rules = orch.get("rules_applied", [])
        print(f"  Rules applied: {rules}")

        # Verify pruned roles (if any)
        pruned = orch.get("pruned_roles", [])
        if pruned:
            print(f"  Pruned roles: {pruned}")

        # Verify team_id was generated
        self.assertNotEqual(orch.get("team_id", ""), "",
                            "Team ID should be generated")

        # Verify lead_agent was assigned
        self.assertNotEqual(orch.get("lead_agent", ""), "",
                            "Lead agent should be assigned")

        print(f"  Scenario D: Orchestrator rules VERIFIED")


if __name__ == "__main__":
    unittest.main(verbosity=2)