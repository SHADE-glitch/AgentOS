#!/usr/bin/env python3
"""
Orchestrator Tests — Phase 7.3

Tests for form_team(), R1-R10 rules, C1-C2 conflict rules, and router integration.
"""

import os
import sys
import unittest

# Ensure imports work
_agent_home = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
sys.path.insert(0, os.path.join(_agent_home, "runtime", "orchestrator"))
sys.path.insert(0, os.path.join(_agent_home, "runtime", "router"))

from orchestrator import Orchestrator, form_team
from team import TeamPlan, load_role_registry
from decision import DecisionContext

BASE = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")


class TestRoleRegistry(unittest.TestCase):
    """Test role registry loading."""

    def test_load_registry(self):
        roles = load_role_registry()
        self.assertIsInstance(roles, dict)
        self.assertGreater(len(roles), 0)

    def test_registry_contains_key_roles(self):
        roles = load_role_registry()
        expected = [
            "system-architect", "backend-architect", "database-engineer",
            "security-engineer", "frontend-architect", "llm-engineer",
            "rag-engineer", "testing-engineer", "devops-engineer",
        ]
        for name in expected:
            self.assertIn(name, roles, f"Registry missing: {name}")

    def test_registry_fields(self):
        roles = load_role_registry()
        for name, entry in roles.items():
            self.assertTrue(entry.name, f"{name} has no name")
            self.assertTrue(entry.domain, f"{name} has no domain")
            self.assertIn(entry.status, ["active", "team-validated"], f"{name} invalid status")


class TestOrchestratorInit(unittest.TestCase):
    """Test orchestrator initialization."""

    def test_load_rules(self):
        orch = Orchestrator()
        orch.load_rules()
        self.assertTrue(orch._loaded)
        self.assertIn("team_rules", orch.__dict__)

    def test_load_role_registry(self):
        orch = Orchestrator()
        orch.load_rules()
        self.assertGreater(len(orch.role_registry), 0)


class TestActivationRules(unittest.TestCase):
    """Test when team formation is triggered."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_single_domain_no_team(self):
        decision = DecisionContext(
            task_text="修复一个简单的 bug",
            intent="debug",
            domains=["backend"],
            primary_domain="backend",
            lead_skill="backend-architect",
            support_skills=[],
            difficulty="easy",
        )
        self.assertFalse(self.orch.should_form_team(decision))

    def test_multi_domain_triggers_team(self):
        decision = DecisionContext(
            task_text="设计一个高并发秒杀系统",
            intent="architecture",
            domains=["backend", "distributed", "database"],
            primary_domain="backend",
            lead_skill="backend-architect",
            support_skills=[],
            difficulty="hard",
        )
        self.assertTrue(self.orch.should_form_team(decision))

    def test_hard_difficulty_triggers_team(self):
        decision = DecisionContext(
            task_text="设计一个复杂的分布式系统",
            intent="coding",
            domains=["backend"],
            primary_domain="backend",
            lead_skill="backend-architect",
            support_skills=[],
            difficulty="hard",
        )
        self.assertTrue(self.orch.should_form_team(decision))

    def test_architecture_intent_triggers_team(self):
        decision = DecisionContext(
            task_text="做一个架构评审",
            intent="architecture",
            domains=["architecture"],
            primary_domain="architecture",
            lead_skill="system-architect",
            support_skills=[],
            difficulty="medium",
        )
        self.assertTrue(self.orch.should_form_team(decision))


class TestBackendTeamFormation(unittest.TestCase):
    """Test backend complex task team formation."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_backend_team(self):
        decision = DecisionContext(
            task_text="设计一个高并发订单系统，需要数据库优化和安全审计",
            intent="architecture",
            domains=["backend", "database", "security"],
            primary_domain="backend",
            lead_skill="backend-architect",
            support_skills=["database-engineer", "security-engineer"],
            difficulty="hard",
        )
        team = self.orch.form_team(decision.task_text, decision)

        self.assertIsInstance(team, TeamPlan)
        self.assertEqual(team.lead_agent, "backend-architect")
        self.assertIn("database-engineer", team.support_agents)
        self.assertIn("security-engineer", team.support_agents)
        self.assertIn("backend", team.domains)
        self.assertGreater(len(team.rules_applied), 0)


class TestAITeamFormation(unittest.TestCase):
    """Test AI task team formation."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_rag_team(self):
        decision = DecisionContext(
            task_text="设计一个 RAG 检索系统，使用向量数据库",
            intent="coding",
            domains=["ai", "backend"],
            primary_domain="ai",
            lead_skill="rag-engineer",
            support_skills=["backend-architect"],
            difficulty="medium",
        )
        team = self.orch.form_team(decision.task_text, decision)

        self.assertEqual(team.lead_agent, "rag-engineer")
        self.assertIn("backend-architect", team.support_agents)
        # R4 should add rag-engineer if not lead, but here rag is lead
        # R3 should add database-engineer if database in domains
        self.assertIn("ai", team.domains)


class TestSecurityTeamFormation(unittest.TestCase):
    """Test security task team formation."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_security_team(self):
        decision = DecisionContext(
            task_text="进行 PCI DSS 安全审计",
            intent="security",
            domains=["security", "backend"],
            primary_domain="security",
            lead_skill="security-engineer",
            support_skills=["backend-architect"],
            difficulty="medium",
        )
        team = self.orch.form_team(decision.task_text, decision)

        self.assertEqual(team.lead_agent, "security-engineer")
        self.assertIn("backend-architect", team.support_agents)


class TestSimpleTaskSingleAgent(unittest.TestCase):
    """Test simple task returns single-agent plan."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_simple_task(self):
        decision = DecisionContext(
            task_text="修复一个简单的 CSS 样式问题",
            intent="debug",
            domains=["frontend"],
            primary_domain="frontend",
            lead_skill="frontend-architect",
            support_skills=[],
            difficulty="easy",
        )
        team = self.orch.form_team(decision.task_text, decision)

        # Should not form a multi-agent team
        self.assertFalse(self.orch.should_form_team(decision))
        # But form_team still works — returns single-agent
        self.assertEqual(team.lead_agent, "frontend-architect")
        self.assertEqual(len(team.support_agents), 0)


class TestDuplicateRoleRemoval(unittest.TestCase):
    """Test C2: duplicate/unknown role pruning."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_unknown_role_pruned(self):
        decision = DecisionContext(
            task_text="设计系统架构",
            intent="architecture",
            domains=["architecture"],
            primary_domain="architecture",
            lead_skill="system-architect",
            support_skills=["unknown-role-xyz", "technical-reviewer"],
            difficulty="hard",
        )
        team = self.orch.form_team(decision.task_text, decision)

        # unknown-role-xyz should be pruned
        all_roles = [team.lead_agent] + team.support_agents
        self.assertNotIn("unknown-role-xyz", all_roles)
        self.assertTrue(
            any(p["role"] == "unknown-role-xyz" for p in team.pruned_roles),
            "Pruned role should be recorded"
        )

    def test_duplicate_support_deduped(self):
        decision = DecisionContext(
            task_text="优化数据库性能",
            intent="optimization",
            domains=["database", "backend"],
            primary_domain="database",
            lead_skill="database-engineer",
            support_skills=["backend-architect", "database-engineer"],  # duplicate
            difficulty="medium",
        )
        team = self.orch.form_team(decision.task_text, decision)

        # Support should not contain lead, and no duplicates
        self.assertNotIn(team.lead_agent, team.support_agents)
        self.assertEqual(len(team.support_agents), len(set(team.support_agents)))


class TestRouterIntegration(unittest.TestCase):
    """Test integration with Router DecisionContext."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_router_to_orchestrator(self):
        """Simulate: Router.route() → Orchestrator.form_team()."""
        # Simulate router output
        decision = DecisionContext(
            task_text="设计一个高并发秒杀系统，需要数据库分库分表和安全防护",
            intent="architecture",
            domains=["backend", "distributed", "database", "security"],
            primary_domain="backend",
            lead_skill="backend-architect",
            support_skills=["system-architect"],
            difficulty="hard",
            confidence="low",
        )
        team = self.orch.form_team(decision.task_text, decision)

        self.assertIsInstance(team, TeamPlan)
        self.assertEqual(team.lead_agent, "backend-architect")
        self.assertGreater(len(team.support_agents), 0)
        self.assertEqual(team.domains, decision.domains)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing systems."""

    def test_team_plan_to_dict(self):
        team = TeamPlan(
            team_id="test-team",
            lead_agent="backend-architect",
            support_agents=["database-engineer"],
            reasoning="Test",
            domains=["backend"],
            rules_applied=["C1: lead = backend-architect"],
            pruned_roles=[],
        )
        d = team.to_dict()
        self.assertEqual(d["team_id"], "test-team")
        self.assertEqual(d["lead_agent"], "backend-architect")
        self.assertIsInstance(d["support_agents"], list)


class TestTeamSizeCap(unittest.TestCase):
    """Test C5: team size cap at 7."""

    def setUp(self):
        self.orch = Orchestrator()
        self.orch.load_rules()

    def test_team_size_capped(self):
        decision = DecisionContext(
            task_text="设计一个跨领域的复杂系统，涉及前端后端数据库安全分布式AI测试",
            intent="architecture",
            domains=["backend", "frontend", "database", "security", "distributed", "ai", "testing"],
            primary_domain="backend",
            lead_skill="backend-architect",
            support_skills=[],
            difficulty="hard",
        )
        team = self.orch.form_team(decision.task_text, decision)

        total = 1 + len(team.support_agents)
        self.assertLessEqual(total, 7, f"Team size {total} exceeds cap of 7")


if __name__ == "__main__":
    unittest.main()
