"""
Router Unit Tests — Phase 7.1

Covers core routing rules against the 50 benchmark scenarios
from tests/router-benchmark.md.
"""

import os
import sys
import unittest

# Add router module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from runtime.router.router import Router
from runtime.router.decision import DecisionContext, ClassificationResult


class TestRouterClassification(unittest.TestCase):
    """Test classification (intent + domain) accuracy."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()
        cls.router.load_rules()

    def test_intent_detection_backend(self):
        """Intent: backend tasks should classify as coding/architecture/data."""
        cases = [
            ("Spring Boot 项目架构设计", "architecture"),
            ("高并发秒杀系统设计", "architecture"),
            ("MySQL SQL 慢查询优化", "optimization"),
            ("订单服务拆分方案", "architecture"),
            ("分布式事务设计", "architecture"),
            ("支付系统接口设计", "architecture"),
            ("Redis 缓存和数据库一致性设计", "data"),
            ("微服务治理方案", "architecture"),
            ("Redis 缓存击穿排查", "coding"),
            ("JVM 性能诊断", "optimization"),
        ]
        for task, expected_intent in cases:
            with self.subTest(task=task):
                c = self.router.classify(task)
                self.assertEqual(c.category, expected_intent,
                                 f"'{task}' → expected '{expected_intent}', got '{c.category}'")

    def test_domain_detection_backend(self):
        """Domain: backend tasks should detect backend domain."""
        cases = [
            ("Spring Boot 项目架构设计", "backend"),
            ("订单服务拆分方案", "backend"),
            ("支付系统接口设计", "backend"),
            ("微服务治理方案", "backend"),
        ]
        for task, expected_domain in cases:
            with self.subTest(task=task):
                c = self.router.classify(task)
                self.assertIn(expected_domain, c.domains,
                              f"'{task}' → expected domain '{expected_domain}', got {c.domains}")

    def test_domain_detection_database(self):
        """Domain: database tasks should detect database domain."""
        cases = [
            ("MySQL SQL 慢查询优化", "database"),
            ("Redis 缓存击穿排查", "database"),
            ("Redis 缓存和数据库一致性设计", "database"),
        ]
        for task, expected_domain in cases:
            with self.subTest(task=task):
                c = self.router.classify(task)
                self.assertIn(expected_domain, c.domains,
                              f"'{task}' → expected domain '{expected_domain}', got {c.domains}")

    def test_ai_scenarios(self):
        """AI scenarios should detect ai domain."""
        cases = [
            ("RAG 系统设计", "ai"),
            ("Agent 工作流设计", "ai"),
            ("Prompt 优化", "ai"),
            ("构建 LLM 应用接入层", "ai"),
            ("向量库选型与召回策略", "ai"),
            ("AI 应用安全评审", "security"),
            ("LLM 评估方案设计", "ai"),
            ("MCP 协议集成设计", "ai"),
            ("AI 编码助手方案评审", "ai"),
            ("RAG 召回失败排查", "ai"),
        ]
        for task, expected_domain in cases:
            with self.subTest(task=task):
                c = self.router.classify(task)
                self.assertIn(expected_domain, c.domains,
                              f"'{task}' → expected domain '{expected_domain}', got {c.domains}")

    def test_frontend_scenarios(self):
        """Frontend scenarios should detect frontend domain."""
        cases = [
            ("React 性能优化", "frontend"),
            ("前端工程化方案设计", "frontend"),
            ("Vue 组件设计与状态管理", "frontend"),
            ("页面加载性能优化", "frontend"),
            ("大前端项目脚手架设计", "frontend"),
            ("前端接口封装设计", "frontend"),
            ("前端布局和渲染问题排查", "frontend"),
            ("前端代码审查", "frontend"),
            ("前端错误边界设计", "frontend"),
        ]
        for task, expected_domain in cases:
            with self.subTest(task=task):
                c = self.router.classify(task)
                self.assertIn(expected_domain, c.domains,
                              f"'{task}' → expected domain '{expected_domain}', got {c.domains}")

    def test_architecture_scenarios(self):
        """Architecture scenarios should detect architecture domain."""
        cases = [
            ("系统设计：电商平台", "architecture"),
            ("高并发日志系统设计", "architecture"),
            ("技术方案评审", "architecture"),
            ("服务拆分评审", "architecture"),
            ("消息队列选型", "distributed"),
            ("系统扩容方案", "architecture"),
            ("服务熔断方案设计", "architecture"),
            ("架构设计评审", "architecture"),
            ("多租户系统架构", "architecture"),
            ("缓存架构设计", "architecture"),
        ]
        for task, expected_domain in cases:
            with self.subTest(task=task):
                c = self.router.classify(task)
                self.assertIn(expected_domain, c.domains,
                              f"'{task}' → expected domain '{expected_domain}', got {c.domains}")


class TestRouterSkillSelection(unittest.TestCase):
    """Test lead skill selection accuracy."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()
        cls.router.load_rules()

    def test_lead_skill_backend(self):
        """Backend scenarios should select correct lead skill."""
        cases = [
            ("Spring Boot 项目架构设计", "backend-architect"),
            ("订单服务拆分方案", "backend-architect"),
            ("支付系统接口设计", "backend-architect"),
            ("JVM 性能诊断", "backend-architect"),
        ]
        for task, expected_lead in cases:
            with self.subTest(task=task):
                d = self.router.route(task)
                self.assertEqual(d.lead_skill, expected_lead,
                                 f"'{task}' → expected lead '{expected_lead}', got '{d.lead_skill}'")

    def test_lead_skill_database(self):
        """Database scenarios should select database-engineer."""
        cases = [
            ("MySQL SQL 慢查询优化", "database-engineer"),
            ("Redis 缓存击穿排查", "database-engineer"),
            ("Redis 缓存和数据库一致性设计", "database-engineer"),
        ]
        for task, expected_lead in cases:
            with self.subTest(task=task):
                d = self.router.route(task)
                self.assertEqual(d.lead_skill, expected_lead,
                                 f"'{task}' → expected lead '{expected_lead}', got '{d.lead_skill}'")

    def test_lead_skill_ai(self):
        """AI scenarios should select correct lead skill."""
        cases = [
            ("RAG 系统设计", "rag-engineer"),
            ("Agent 工作流设计", "agent-engineer"),
            ("Prompt 优化", "prompt-engineer"),
            ("构建 LLM 应用接入层", "llm-engineer"),
            ("向量库选型与召回策略", "rag-engineer"),
            ("RAG 召回失败排查", "rag-engineer"),
        ]
        for task, expected_lead in cases:
            with self.subTest(task=task):
                d = self.router.route(task)
                self.assertEqual(d.lead_skill, expected_lead,
                                 f"'{task}' → expected lead '{expected_lead}', got '{d.lead_skill}'")

    def test_lead_skill_architecture(self):
        """Architecture scenarios should select system-architect."""
        cases = [
            ("系统设计：电商平台", "system-architect"),
            ("高并发日志系统设计", "system-architect"),
            ("多租户系统架构", "system-architect"),
            ("缓存架构设计", "system-architect"),
        ]
        for task, expected_lead in cases:
            with self.subTest(task=task):
                d = self.router.route(task)
                self.assertEqual(d.lead_skill, expected_lead,
                                 f"'{task}' → expected lead '{expected_lead}', got '{d.lead_skill}'")

    def test_lead_skill_review(self):
        """Review scenarios should select code-reviewer or technical-reviewer."""
        cases = [
            ("技术方案评审", "technical-reviewer"),
            ("架构设计评审", "technical-reviewer"),
            ("前端代码审查", "code-reviewer"),
        ]
        for task, expected_lead in cases:
            with self.subTest(task=task):
                d = self.router.route(task)
                self.assertEqual(d.lead_skill, expected_lead,
                                 f"'{task}' → expected lead '{expected_lead}', got '{d.lead_skill}'")

    def test_lead_skill_security(self):
        """Security scenarios should select security-engineer."""
        d = self.router.route("AI 应用安全评审")
        self.assertEqual(d.lead_skill, "security-engineer")


class TestRouterDecisionContext(unittest.TestCase):
    """Test DecisionContext completeness and shape."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()
        cls.router.load_rules()

    def test_decision_has_required_fields(self):
        """DecisionContext must contain all required fields."""
        d = self.router.route("分析 MySQL 慢查询问题")
        required = [
            "task_text", "intent", "domains", "primary_domain",
            "lead_skill", "support_skills", "confidence", "difficulty",
            "memory_influence", "memory_retrieved", "rules_applied",
            "started_at", "completed_at",
        ]
        for field in required:
            self.assertTrue(hasattr(d, field),
                            f"DecisionContext missing field: {field}")

    def test_decision_to_dict(self):
        """DecisionContext.to_dict() should produce valid dict."""
        d = self.router.route("分析 MySQL 慢查询问题")
        result = d.to_dict()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["lead_skill"], d.lead_skill)

    def test_decision_to_trace_dict(self):
        """DecisionContext.to_trace_dict() should produce trace-format dict."""
        d = self.router.route("分析 MySQL 慢查询问题")
        result = d.to_trace_dict()
        self.assertIsInstance(result, dict)
        self.assertIn("lead_skill", result)
        self.assertIn("support_skills", result)

    def test_always_has_lead_skill(self):
        """Every route must produce a non-empty lead_skill."""
        tasks = [
            "分析 MySQL 慢查询",
            "Spring Boot 项目",
            "asdfghjkl",  # nonsense input
            "",  # empty input
        ]
        for task in tasks:
            with self.subTest(task=task):
                d = self.router.route(task)
                self.assertIsNotNone(d.lead_skill)
                self.assertNotEqual(d.lead_skill, "")
                self.assertNotEqual(d.lead_skill, "None")

    def test_confidence_levels(self):
        """Confidence should be high/medium/low."""
        d = self.router.route("分析 MySQL 慢查询问题")
        self.assertIn(d.confidence, ["high", "medium", "low"])


class TestRouterMemoryInfluence(unittest.TestCase):
    """Test memory context integration."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()
        cls.router.load_rules()

    def test_no_memory_context(self):
        """Without memory context, influence should be 'none'."""
        d = self.router.route("分析 MySQL 慢查询问题")
        self.assertEqual(d.memory_influence, "none")
        self.assertEqual(d.memory_retrieved, 0)

    def test_with_memory_context_weak(self):
        """With 1-2 memories, influence should be 'weak'."""
        ctx = {"memories": [{"memory_id": "T-001"}]}
        d = self.router.route("分析 MySQL 慢查询问题", memory_context=ctx)
        self.assertEqual(d.memory_influence, "weak")
        self.assertEqual(d.memory_retrieved, 1)

    def test_with_memory_context_confirmation(self):
        """With 3+ memories, influence should be 'confirmation'."""
        ctx = {"memories": [{"memory_id": f"T-00{i}"} for i in range(1, 4)]}
        d = self.router.route("分析 MySQL 慢查询问题", memory_context=ctx)
        self.assertEqual(d.memory_influence, "confirmation")
        self.assertEqual(d.memory_retrieved, 3)

    def test_empty_memory_context(self):
        """Empty memories list should be 'none'."""
        ctx = {"memories": []}
        d = self.router.route("分析 MySQL 慢查询问题", memory_context=ctx)
        self.assertEqual(d.memory_influence, "none")


class TestRouterClassificationBackwardCompat(unittest.TestCase):
    """Test ClassificationResult backward compatibility with old classify_task()."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()
        cls.router.load_rules()

    def test_returns_category(self):
        """ClassificationResult must have 'category' field (backward compat)."""
        c = self.router.classify("分析 MySQL 慢查询问题")
        self.assertIsInstance(c.category, str)
        self.assertNotEqual(c.category, "")

    def test_returns_domains_list(self):
        """ClassificationResult.domains must be a list."""
        c = self.router.classify("分析 MySQL 慢查询问题")
        self.assertIsInstance(c.domains, list)
        self.assertGreater(len(c.domains), 0)

    def test_returns_roles_list(self):
        """ClassificationResult.roles must be a list."""
        c = self.router.classify("分析 MySQL 慢查询问题")
        self.assertIsInstance(c.roles, list)

    def test_returns_keywords_list(self):
        """ClassificationResult.keywords must be a list."""
        c = self.router.classify("分析 MySQL 慢查询问题")
        self.assertIsInstance(c.keywords, list)

    def test_returns_difficulty(self):
        """ClassificationResult.difficulty must be easy/medium/hard."""
        c = self.router.classify("分析 MySQL 慢查询问题")
        self.assertIn(c.difficulty, ["easy", "medium", "hard"])

    def test_to_dict(self):
        """ClassificationResult.to_dict() should produce a dict."""
        c = self.router.classify("分析 MySQL 慢查询问题")
        result = c.to_dict()
        self.assertIsInstance(result, dict)
        self.assertIn("category", result)
        self.assertIn("domains", result)
        self.assertIn("roles", result)
        self.assertIn("keywords", result)
        self.assertIn("difficulty", result)


class TestRouterBenchmarkCoverage(unittest.TestCase):
    """Run all 50 benchmark scenarios and measure accuracy."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()
        cls.router.load_rules()

        # Full benchmark: (task_text, expected_lead)
        cls.benchmark = [
            # Backend (1-10)
            ("Spring Boot 项目架构设计", "backend-architect"),
            ("Redis 缓存击穿排查", "database-engineer"),
            ("高并发秒杀系统设计", "system-architect"),
            ("MySQL SQL 慢查询优化", "database-engineer"),
            ("订单服务拆分方案", "backend-architect"),
            ("分布式事务设计", "system-architect"),
            ("支付系统接口设计", "backend-architect"),
            ("Redis 缓存和数据库一致性设计", "database-engineer"),
            ("微服务治理方案", "backend-architect"),
            ("JVM 性能诊断", "backend-architect"),
            # AI (11-20)
            ("RAG 系统设计", "rag-engineer"),
            ("Agent 工作流设计", "agent-engineer"),
            ("Prompt 优化", "prompt-engineer"),
            ("构建 LLM 应用接入层", "llm-engineer"),
            ("向量库选型与召回策略", "rag-engineer"),
            ("AI 应用安全评审", "security-engineer"),
            ("LLM 评估方案设计", "llm-engineer"),
            ("MCP 协议集成设计", "agent-engineer"),
            ("AI 编码助手方案评审", "prompt-engineer"),
            ("RAG 召回失败排查", "rag-engineer"),
            # Frontend (21-30)
            ("React 性能优化", "frontend-performance"),
            ("前端工程化方案设计", "frontend-architect"),
            ("Vue 组件设计与状态管理", "frontend-architect"),
            ("页面加载性能优化", "frontend-performance"),
            ("大前端项目脚手架设计", "frontend-architect"),
            ("前端接口封装设计", "frontend-architect"),
            ("前端布局和渲染问题排查", "frontend-performance"),
            ("前端代码审查", "code-reviewer"),
            ("构建缓存优化方案", "devops-engineer"),
            ("前端错误边界设计", "frontend-architect"),
            # Architecture (31-40)
            ("系统设计：电商平台", "system-architect"),
            ("高并发日志系统设计", "system-architect"),
            ("技术方案评审", "technical-reviewer"),
            ("服务拆分评审", "system-architect"),
            ("消息队列选型", "system-architect"),
            ("系统扩容方案", "system-architect"),
            ("服务熔断方案设计", "system-architect"),
            ("架构设计评审", "technical-reviewer"),
            ("多租户系统架构", "system-architect"),
            ("缓存架构设计", "system-architect"),
            # Learning (41-50)
            ("学习路线规划", "learning-strategist"),
            ("项目陪练", "project-mentor"),
            ("Java 后端面试准备", "interview-coach"),
            ("我想提升后端架构能力", "learning-strategist"),
            ("看懂项目结构和模块职责", "project-mentor"),
            ("面试中被问到数据库索引原理", "interview-coach"),
            ("我想做一个 Java 项目练习", "learning-strategist"),
            ("项目中我不懂为什么要这样设计", "project-mentor"),
            ("服务拆分问题如何理解", "project-mentor"),
            ("准备系统设计面试", "interview-coach"),
        ]

    def test_full_benchmark_accuracy(self):
        """Run all 50 benchmark scenarios and verify accuracy >= 70%."""
        correct = 0
        total = len(self.benchmark)
        failures = []

        for task, expected_lead in self.benchmark:
            d = self.router.route(task)
            if d.lead_skill == expected_lead:
                correct += 1
            else:
                failures.append(f"  '{task}': expected '{expected_lead}', got '{d.lead_skill}'")

        accuracy = correct / total * 100 if total > 0 else 0

        # Report failures
        if failures:
            print(f"\n  Failures ({len(failures)}/{total}):")
            for f in failures:
                print(f)

        print(f"\n  Accuracy: {correct}/{total} = {accuracy:.1f}%")

        # Accept 70%+ as baseline (rules are rule-based, not ML)
        self.assertGreaterEqual(
            accuracy, 70.0,
            f"Benchmark accuracy {accuracy:.1f}% below 70% threshold"
        )


if __name__ == "__main__":
    unittest.main()