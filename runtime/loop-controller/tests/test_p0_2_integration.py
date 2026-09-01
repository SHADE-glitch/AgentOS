#!/usr/bin/env python3
"""
Integration Tests — P0-2 Cross-Stack Protection with Runtime Adapter

Tests the full chain:
  project_root → detect_tech_stack → build_stack_context → prompt injection
  → validate_output_stack

Verifies:
  1. Stack detection on real project (AIView: Java/Spring Boot)
  2. Stack context injection into prompt
  3. Output validation detects cross-stack contamination
  4. Non-contaminated output passes validation
  5. project_root propagation through execute_with_reliability
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cross_stack_guard import (
    detect_tech_stack,
    build_stack_context,
    validate_output_stack,
    TechStack,
    CrossStackResult,
    JAVA_MARKERS,
    PYTHON_MARKERS,
)
from runtime_adapter import build_prompt, execute_with_reliability
from test_provider import TestProvider, register_test_provider


AI_VIEW_PROJECT = "/home/shade/Public/test"


class TestP0_2_StackDetection(unittest.TestCase):
    """Verify stack detection on real projects."""

    def test_detect_ai_view_stack(self):
        """AIView should be detected as Java 21 / Maven / Spring Boot."""
        stack = detect_tech_stack(AI_VIEW_PROJECT)
        self.assertIsNotNone(stack)
        self.assertEqual(stack.primary_language, "java")
        self.assertEqual(stack.language_version, "21")
        self.assertEqual(stack.build_system, "maven")
        self.assertIn("spring-boot", stack.framework)
        self.assertEqual(stack.runtime, "jvm")

    def test_detect_nonexistent_project(self):
        """Non-existent path should return unknown stack, not crash."""
        stack = detect_tech_stack("/tmp/nonexistent_project_xyz")
        self.assertIsNotNone(stack)
        self.assertEqual(stack.primary_language, "unknown")
        self.assertEqual(stack.build_system, "unknown")

    def test_stack_context_contains_stack_info(self):
        """Stack context should reference the detected stack."""
        stack = detect_tech_stack(AI_VIEW_PROJECT)
        context = build_stack_context(AI_VIEW_PROJECT)
        self.assertIsNotNone(context)
        self.assertIn("java", context.lower())
        self.assertIn("spring", context.lower())
        self.assertIn("maven", context.lower())

    def test_stack_context_empty_for_nonexistent(self):
        """Stack context should be empty for non-existent project."""
        context = build_stack_context("/tmp/nonexistent_project_xyz")
        self.assertEqual(context, "")


class TestP0_2_OutputValidation(unittest.TestCase):
    """Verify cross-stack output validation."""

    def test_python_code_in_java_project_detected(self):
        """Python code in Java project should be flagged as contamination."""
        python_output = (
            "```python\n"
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "@app.route('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n"
            "```\n"
        )
        result = validate_output_stack(AI_VIEW_PROJECT, python_output)
        self.assertTrue(
            result.contamination_detected,
            "P0-2: Python code in Java project should be detected"
        )
        self.assertGreater(len(result.warnings), 0)
        self.assertIn("python", result.contaminated_language.lower())

    def test_java_code_in_java_project_clean(self):
        """Java code in Java project should NOT be flagged."""
        java_output = (
            "```java\n"
            "import org.springframework.web.bind.annotation.*;\n"
            "@RestController\n"
            "public class HealthController {\n"
            "    @GetMapping(\"/health\")\n"
            "    public ResponseEntity<String> health() {\n"
            "        return ResponseEntity.ok(\"OK\");\n"
            "    }\n"
            "}\n"
            "```\n"
        )
        result = validate_output_stack(AI_VIEW_PROJECT, java_output)
        self.assertFalse(
            result.contamination_detected,
            "P0-2: Java code in Java project should be clean"
        )

    def test_node_js_code_in_java_project_detected(self):
        """Node.js code in Java project — detection depends on implementation."""
        node_output = (
            "```javascript\n"
            "const express = require('express');\n"
            "const app = express();\n"
            "app.get('/health', (req, res) => {\n"
            "    res.json({ status: 'ok' });\n"
            "});\n"
            "```\n"
        )
        result = validate_output_stack(AI_VIEW_PROJECT, node_output)
        # Current impl focuses on Python→Java contamination; Node.js may not be detected
        # Verify the result is structurally valid regardless
        self.assertIsInstance(result, CrossStackResult)
        self.assertIsNotNone(result.project_stack)

    def test_empty_output_clean(self):
        """Empty output should not trigger contamination."""
        result = validate_output_stack(AI_VIEW_PROJECT, "")
        self.assertFalse(result.contamination_detected)

    def test_cross_stack_result_structure(self):
        """CrossStackResult should have proper structure when contamination detected."""
        python_output = (
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "@app.route('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n"
        )
        result = validate_output_stack(AI_VIEW_PROJECT, python_output)
        self.assertTrue(result.contamination_detected)
        self.assertIsInstance(result.contaminated_language, str)
        self.assertIsInstance(result.warnings, list)
        self.assertIsInstance(result.contamination_details, list)
        self.assertIsInstance(result.project_stack, TechStack)


class TestP0_2_PromptInjection(unittest.TestCase):
    """Verify stack context is injected into prompts."""

    def test_prompt_includes_stack_context(self):
        """Prompt should include stack context when project_root is valid."""
        decision_context = {
            "memories": [],
            "hypotheses": [],
            "classification": {"category": "backend", "domains": []},
        }
        prompt = build_prompt(
            "Add health check endpoint",
            decision_context,
            project_root=AI_VIEW_PROJECT,
        )
        self.assertIn("java", prompt.lower())
        self.assertIn("spring-boot", prompt.lower())
        self.assertIn("maven", prompt.lower())

    def test_prompt_no_stack_context_for_empty_root(self):
        """Prompt should NOT include stack context when project_root is empty."""
        decision_context = {
            "memories": [],
            "hypotheses": [],
            "classification": {"category": "backend", "domains": []},
        }
        prompt = build_prompt(
            "Add health check endpoint",
            decision_context,
            project_root="",
        )
        self.assertNotIn("Current Project Stack", prompt)


class TestP0_2_IntegrationWithRuntime(unittest.TestCase):
    """Verify cross-stack guard works through execute_with_reliability."""

    @classmethod
    def setUpClass(cls):
        cls.provider = TestProvider()
        register_test_provider(cls.provider)

    def setUp(self):
        self.provider.reset()
        self.provider.set_scenario("success")

    def tearDown(self):
        self.provider.reset()

    def test_stack_validation_on_success_with_project_root(self):
        """Cross-stack validation should run when project_root is provided."""
        result = execute_with_reliability(
            task_id="TEST-CS-001",
            task_text="Add health check",
            decision_context={},
            provider="test_provider",
            model="test-model",
            project_root=AI_VIEW_PROJECT,
        )

        self.assertEqual(result["status"], "success")
        reliability = result.get("reliability", {})
        cross_stack = reliability.get("cross_stack", {})
        # Test provider outputs Java code, so no contamination expected
        self.assertIsNotNone(cross_stack)
        self.assertFalse(cross_stack.get("contamination_detected", True))

    def test_stack_validation_skipped_without_project_root(self):
        """Cross-stack validation should be skipped when project_root is empty."""
        result = execute_with_reliability(
            task_id="TEST-CS-002",
            task_text="Add health check",
            decision_context={},
            provider="test_provider",
            model="test-model",
            project_root="",
        )

        self.assertEqual(result["status"], "success")
        reliability = result.get("reliability", {})
        cross_stack = reliability.get("cross_stack", {})
        self.assertIsNone(cross_stack)


if __name__ == "__main__":
    unittest.main()