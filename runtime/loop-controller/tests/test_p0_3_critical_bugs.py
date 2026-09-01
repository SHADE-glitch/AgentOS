#!/usr/bin/env python3
"""
Regression Tests — P0-3: Critical Bug Detection

Tests:
  1. Competing RabbitMQ consumers detection
  2. Competing Kafka consumers detection
  3. Properly isolated consumers (both have @ConditionalOnProperty)
  4. Unisolated dependency detection
  5. No false positives on clean code
  6. Detection on AIView-like project structure

These tests verify the critical bug detector correctly identifies
architecture-level issues in Spring Boot projects.
"""

import sys
import os
import tempfile
import unittest

# Add loop-controller to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from critical_bug_detector import (
    detect_competing_consumers,
    detect_unisolated_dependencies,
    run_critical_bug_detection,
    generate_advisory,
    CompetingConsumerIssue,
    UnisolatedDependencyIssue,
    DetectionResult,
    CONDITIONAL_DEPENDENCIES,
)


def create_java_file(tmpdir, filename, content):
    """Create a Java file in the temp directory."""
    filepath = os.path.join(tmpdir, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


class TestCompetingConsumerDetection(unittest.TestCase):
    """Test detection of competing message consumers."""

    def test_competing_rabbitmq_consumers_no_conditional(self):
        """Two services listening to same queue without @ConditionalOnProperty → CRITICAL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "AiScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;

@Service
public class AiScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {
        // AI scoring logic
    }
}
""")
            create_java_file(tmpdir, "RuleBasedScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;

@Service
public class RuleBasedScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {
        // Rule-based scoring logic
    }
}
""")
            issues = detect_competing_consumers(tmpdir)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].queue_name, "interview.scoring")
            self.assertEqual(len(issues[0].consumers), 2)
            self.assertFalse(issues[0].has_conditional_any)
            self.assertEqual(issues[0].risk_level, "CRITICAL")

    def test_competing_with_partial_conditional(self):
        """One has @ConditionalOnProperty, one doesn't → HIGH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "AiScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Service
@ConditionalOnProperty(name = "app.mode", havingValue = "ai")
public class AiScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {}
}
""")
            create_java_file(tmpdir, "RuleBasedScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;

@Service
public class RuleBasedScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {}
}
""")
            issues = detect_competing_consumers(tmpdir)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].risk_level, "HIGH")
            self.assertTrue(issues[0].has_conditional_any)

    def test_both_conditional(self):
        """Both have @ConditionalOnProperty → MEDIUM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "AiScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Service
@ConditionalOnProperty(name = "app.mode", havingValue = "ai")
public class AiScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {}
}
""")
            create_java_file(tmpdir, "RuleBasedScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Service
@ConditionalOnProperty(name = "app.mode", havingValue = "rule")
public class RuleBasedScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {}
}
""")
            issues = detect_competing_consumers(tmpdir)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].risk_level, "MEDIUM")

    def test_no_competing_single_consumer(self):
        """Single consumer → no issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "ScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;

@Service
public class ScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {}
}
""")
            issues = detect_competing_consumers(tmpdir)
            self.assertEqual(len(issues), 0)

    def test_different_queues_no_competition(self):
        """Two consumers on different queues → no issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "ScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;

@Service
public class ScoringService {
    @RabbitListener(queues = "interview.scoring")
    public void score(String message) {}
}
""")
            create_java_file(tmpdir, "NotificationService.java", """
package com.example.service;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    @RabbitListener(queues = "interview.notification")
    public void notify(String message) {}
}
""")
            issues = detect_competing_consumers(tmpdir)
            self.assertEqual(len(issues), 0)

    def test_ai_view_exact_pattern(self):
        """Exact AIView pattern: InterviewScoringService + RuleBasedScoringService on same queue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "interview/service/InterviewScoringService.java", """
package com.aiview.interview.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import com.aiview.agent.ai.ChatClient;
import com.aiview.config.AiProperties;

@Service
@RequiredArgsConstructor
public class InterviewScoringService {
    private final ChatClient chatClient;
    private final AiProperties aiProperties;

    @RabbitListener(queues = "aiview.interview.scoring")
    public void score(ScoringMessage message) {
        // AI-based scoring
    }
}
""")
            create_java_file(tmpdir, "interview/service/RuleBasedScoringService.java", """
package com.aiview.interview.service;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Service
@ConditionalOnProperty(name = "app.interview.mode", havingValue = "rule", matchIfMissing = true)
public class RuleBasedScoringService {
    @RabbitListener(queues = "aiview.interview.scoring")
    public void score(ScoringMessage message) {
        // Rule-based scoring
    }
}
""")
            issues = detect_competing_consumers(tmpdir)
            self.assertEqual(len(issues), 1)
            # InterviewScoringService has no @ConditionalOnProperty → HIGH
            self.assertEqual(issues[0].risk_level, "HIGH")
            self.assertTrue(issues[0].has_conditional_any)


class TestUnisolatedDependencyDetection(unittest.TestCase):
    """Test detection of unisolated dependencies."""

    def test_direct_chatclient_dependency(self):
        """Service directly depends on ChatClient without @ConditionalOnProperty → HIGH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "InterviewScoringService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class InterviewScoringService {
    private final ChatClient chatClient;
    private final AiProperties aiProperties;

    @RabbitListener(queues = "interview.scoring")
    public void score(ScoringMessage message) {
        // AI scoring
    }
}
""")
            issues = detect_unisolated_dependencies(tmpdir)
            self.assertGreater(len(issues), 0)
            found = [i for i in issues if i.dependency == "ChatClient"]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].risk_level, "HIGH")
            self.assertFalse(found[0].has_conditional)

    def test_with_conditional_property(self):
        """Service with @ConditionalOnProperty → no issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "LegacyService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import lombok.RequiredArgsConstructor;

@Service
@ConditionalOnProperty(name = "app.mode", havingValue = "ai")
@RequiredArgsConstructor
public class LegacyService {
    private final ChatClient chatClient;
}
""")
            issues = detect_unisolated_dependencies(tmpdir)
            self.assertEqual(len(issues), 0)

    def test_legacy_skipped(self):
        """Files in legacy/ directory should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "legacy/ai/LegacyService.java", """
package com.example.legacy.ai;

import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class LegacyService {
    private final ChatClient chatClient;
}
""")
            issues = detect_unisolated_dependencies(tmpdir)
            self.assertEqual(len(issues), 0)

    def test_agent_ai_skipped(self):
        """Files in agent/ai/ directory should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "agent/ai/EmbeddingClient.java", """
package com.example.agent.ai;

public interface EmbeddingClient {
    List<float[]> embedAll(List<String> texts);
}
""")
            issues = detect_unisolated_dependencies(tmpdir)
            self.assertEqual(len(issues), 0)  # Interface, should be skipped anyway

    def test_clean_service_no_issue(self):
        """Service without AI dependencies → no issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "UserService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
}
""")
            issues = detect_unisolated_dependencies(tmpdir)
            self.assertEqual(len(issues), 0)


class TestFullDetection(unittest.TestCase):
    """Test the full detection pipeline."""

    def test_clean_project_no_issues(self):
        """Clean project with no patterns → zero issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_java_file(tmpdir, "UserService.java", """
package com.example.service;

import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
}
""")
            result = run_critical_bug_detection(tmpdir)
            self.assertEqual(result.total_issues, 0)
            self.assertEqual(result.critical_count, 0)
            self.assertEqual(result.high_count, 0)

    def test_ai_view_like_project(self):
        """AIView-like project with competing consumers AND unisolated deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Competing consumers
            create_java_file(tmpdir, "interview/service/InterviewScoringService.java", """
package com.aiview.interview.service;

import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class InterviewScoringService {
    private final ChatClient chatClient;
    @RabbitListener(queues = "aiview.interview.scoring")
    public void score(ScoringMessage message) {}
}
""")
            create_java_file(tmpdir, "interview/service/RuleBasedScoringService.java", """
package com.aiview.interview.service;

import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Service
@ConditionalOnProperty(name = "app.interview.mode", havingValue = "rule")
public class RuleBasedScoringService {
    @RabbitListener(queues = "aiview.interview.scoring")
    public void score(ScoringMessage message) {}
}
""")
            # Unisolated dependency
            create_java_file(tmpdir, "rag/service/RagService.java", """
package com.aiview.rag.service;

import org.springframework.stereotype.Service;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class RagService {
    private final EmbeddingClient embeddingClient;
    public void addContent(String content) {}
}
""")

            result = run_critical_bug_detection(tmpdir)
            self.assertGreater(result.total_issues, 0)

            # Should have 1 competing consumer (HIGH) + 1 unisolated dep (HIGH)
            self.assertEqual(len(result.competing_consumers), 1)
            self.assertGreaterEqual(len(result.unisolated_dependencies), 1)

            # Generate advisories
            advisories = generate_advisory(result)
            self.assertGreater(len(advisories), 0)


class TestAdvisoryGeneration(unittest.TestCase):
    """Test advisory message generation."""

    def test_critical_advisory(self):
        """CRITICAL issue should generate CRITICAL_ARCHITECTURE_RISK advisory."""
        result = DetectionResult(
            project_root="/tmp/test",
            detected_at="2026-01-01T00:00:00Z",
            competing_consumers=[
                CompetingConsumerIssue(
                    queue_name="test.queue",
                    consumers=["ServiceA (path/a.java)", "ServiceB (path/b.java)"],
                    has_conditional_any=False,
                    risk_level="CRITICAL",
                )
            ],
            total_issues=1,
            critical_count=1,
        )
        advisories = generate_advisory(result)
        self.assertEqual(len(advisories), 1)
        self.assertIn("CRITICAL_ARCHITECTURE_RISK", advisories[0])
        self.assertIn("competing consumers", advisories[0].lower())
        self.assertIn("conditional bean isolation", advisories[0].lower())
        self.assertIn("message routing", advisories[0].lower())

    def test_empty_result_no_advisory(self):
        """No issues → no advisories."""
        result = DetectionResult(
            project_root="/tmp/test",
            detected_at="2026-01-01T00:00:00Z",
        )
        advisories = generate_advisory(result)
        self.assertEqual(len(advisories), 0)


if __name__ == "__main__":
    unittest.main()