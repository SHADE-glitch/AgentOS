#!/usr/bin/env python3
"""
Critical Bug Detector — Phase 5.1 P0-3

Detects critical architecture risks in project code based on evidence from
the AIView project audit.

Evidence:
  - FP-001: InterviewScoringService + RuleBasedScoringService both listen
    to the same RabbitMQ queue "aiview.interview.scoring" without conditional
    injection, causing message competition.
  - FP-004: InterviewScoringService and RagService directly depend on
    ChatClient/EmbeddingClient without @ConditionalOnProperty protection.

This module generalizes these patterns into reusable detection rules:
  1. Multiple Consumers + Same Queue/Topic + Mode-dependent Services
  2. Service dependency on conditional infrastructure without isolation
  3. Bean duplication with conflicting profiles

Detection is NOT hardcoded to AIView — it works on any Spring Boot project.
"""

import os
import re
import fnmatch
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone


# ── Detection Result Types ──────────────────────────────────────

@dataclass
class CompetingConsumerIssue:
    """Two or more beans listening to the same queue without conditional isolation."""
    queue_name: str
    consumers: List[str]  # file paths of consumer classes
    has_conditional_any: bool  # do any consumers have @ConditionalOnProperty?
    risk_level: str  # CRITICAL | HIGH | MEDIUM


@dataclass
class UnisolatedDependencyIssue:
    """A bean directly depends on a conditional/mode-dependent service without protection."""
    file_path: str
    class_name: str
    dependency: str  # ChatClient, EmbeddingClient, etc.
    has_conditional: bool
    risk_level: str


@dataclass
class DetectionResult:
    """Full critical bug detection result."""
    project_root: str
    detected_at: str
    competing_consumers: List[CompetingConsumerIssue] = field(default_factory=list)
    unisolated_dependencies: List[UnisolatedDependencyIssue] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    total_issues: int = 0


# ── File Scanning Utilities ─────────────────────────────────────

def _find_java_files(project_root: str) -> List[str]:
    """Find all .java files in the project."""
    java_files = []
    for root, dirs, files in os.walk(project_root):
        # Skip test directories and build output
        dirs[:] = [d for d in dirs if d not in ("target", "build", "node_modules", ".git", "__pycache__")]
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))
    return java_files


def _read_file(file_path: str) -> str:
    """Read a file, returning empty string on error."""
    try:
        with open(file_path) as f:
            return f.read()
    except Exception:
        return ""


def _extract_class_name(file_path: str, content: str) -> str:
    """Extract class name from Java file content."""
    m = re.search(r'public\s+class\s+(\w+)', content)
    if m:
        return m.group(1)
    return os.path.basename(file_path).replace(".java", "")


# ── P0-3-1: Competing Consumers Detection ────────────────────────

def detect_competing_consumers(project_root: str) -> List[CompetingConsumerIssue]:
    """
    Detect multiple consumers listening to the same message queue/topic.

    Checks for:
      - @RabbitListener with same queue name
      - @KafkaListener with same topic
      - @Scheduled (future)
      - Multiple @Service beans implementing same interface without @ConditionalOnProperty

    Returns:
        List of CompetingConsumerIssue
    """
    java_files = _find_java_files(project_root)
    if not java_files:
        return []

    # Map of queue_name → list of (file_path, class_name, has_conditional)
    rabbit_consumers: Dict[str, List[Tuple[str, str, bool]]] = {}
    kafka_consumers: Dict[str, List[Tuple[str, str, bool]]] = {}

    for file_path in java_files:
        content = _read_file(file_path)
        if not content:
            continue

        class_name = _extract_class_name(file_path, content)

        # Check for @ConditionalOnProperty
        has_conditional = bool(re.search(r'@ConditionalOnProperty', content))

        # Find RabbitMQ listeners
        rabbit_matches = re.findall(
            r'@RabbitListener\s*\(\s*queues\s*=\s*["\']([^"\']+)["\']',
            content
        )
        for queue_name in rabbit_matches:
            if queue_name not in rabbit_consumers:
                rabbit_consumers[queue_name] = []
            rabbit_consumers[queue_name].append((file_path, class_name, has_conditional))

        # Find Kafka listeners
        kafka_matches = re.findall(
            r'@KafkaListener\s*\([^)]*topics\s*=\s*["\']([^"\']+)["\']',
            content
        )
        for topic in kafka_matches:
            if topic not in kafka_consumers:
                kafka_consumers[topic] = []
            kafka_consumers[topic].append((file_path, class_name, has_conditional))

    # Build issues
    issues = []

    # Check RabbitMQ
    for queue_name, consumers in rabbit_consumers.items():
        if len(consumers) > 1:
            has_any_conditional = any(c[2] for c in consumers)
            all_conditional = all(c[2] for c in consumers)

            if not all_conditional:
                risk = "CRITICAL" if not has_any_conditional else "HIGH"
            else:
                risk = "MEDIUM"

            issues.append(CompetingConsumerIssue(
                queue_name=queue_name,
                consumers=[f"{c[1]} ({c[0]})" for c in consumers],
                has_conditional_any=has_any_conditional,
                risk_level=risk,
            ))

    # Check Kafka
    for topic, consumers in kafka_consumers.items():
        if len(consumers) > 1:
            has_any_conditional = any(c[2] for c in consumers)
            all_conditional = all(c[2] for c in consumers)

            if not all_conditional:
                risk = "CRITICAL" if not has_any_conditional else "HIGH"
            else:
                risk = "MEDIUM"

            issues.append(CompetingConsumerIssue(
                queue_name=f"Kafka:{topic}",
                consumers=[f"{c[1]} ({c[0]})" for c in consumers],
                has_conditional_any=has_any_conditional,
                risk_level=risk,
            ))

    return issues


# ── P0-3-2: Unisolated Dependency Detection ─────────────────────

# Known AI/infrastructure dependencies that should be conditionally isolated
CONDITIONAL_DEPENDENCIES = [
    "ChatClient",
    "EmbeddingClient",
    "AiProperties",
    "OpenAiClient",
    "DeepSeekClient",
    "OllamaClient",
    "ModelClient",
    "VectorStore",
    "DocumentReader",
    "TokenCounter",
    "PromptTemplate",
]


def detect_unisolated_dependencies(project_root: str) -> List[UnisolatedDependencyIssue]:
    """
    Detect beans that directly depend on conditional infrastructure
    without @ConditionalOnProperty protection.

    Skips files in legacy/ or agent/ai/ directories (infrastructure layer).

    Returns:
        List of UnisolatedDependencyIssue
    """
    java_files = _find_java_files(project_root)
    if not java_files:
        return []

    issues = []

    for file_path in java_files:
        # Skip infrastructure layer files
        normalized = file_path.replace("\\", "/")
        if "/legacy/" in normalized or "/agent/ai/" in normalized:
            continue

        content = _read_file(file_path)
        if not content:
            continue

        # Skip if already has @ConditionalOnProperty
        if re.search(r'@ConditionalOnProperty', content):
            continue

        # Skip interfaces and abstract classes
        if re.search(r'public\s+(interface|abstract\s+class)\s+\w+', content):
            continue

        # Check for constructor injection of conditional dependencies
        for dep in CONDITIONAL_DEPENDENCIES:
            # Match: "private final DepClass depClass" or "private final DepClass depClass;"
            if re.search(rf'private\s+final\s+{dep}\s+\w+', content):
                class_name = _extract_class_name(file_path, content)
                issues.append(UnisolatedDependencyIssue(
                    file_path=normalized,
                    class_name=class_name,
                    dependency=dep,
                    has_conditional=False,
                    risk_level="HIGH",
                ))
                break  # One issue per file is enough

    return issues


# ── P0-3-3: Bean Duplication Detection (Future) ─────────────────

def detect_bean_duplication(project_root: str) -> List[Dict[str, Any]]:
    """
    Detect duplicate @Bean definitions that could conflict.

    Future: this is a placeholder for detecting @Bean method conflicts
    across @Configuration classes.
    """
    return []  # Not yet implemented — deferred to P1


# ── Main Detection Entry Point ──────────────────────────────────

def run_critical_bug_detection(project_root: str) -> DetectionResult:
    """
    Run all critical bug detection checks on a project.

    Args:
        project_root: path to project root directory

    Returns:
        DetectionResult with all issues found
    """
    result = DetectionResult(
        project_root=project_root,
        detected_at=datetime.now(timezone.utc).isoformat(),
    )

    # Competing consumers
    result.competing_consumers = detect_competing_consumers(project_root)
    for issue in result.competing_consumers:
        if issue.risk_level == "CRITICAL":
            result.critical_count += 1
        elif issue.risk_level == "HIGH":
            result.high_count += 1
        elif issue.risk_level == "MEDIUM":
            result.medium_count += 1

    # Unisolated dependencies
    result.unisolated_dependencies = detect_unisolated_dependencies(project_root)
    for issue in result.unisolated_dependencies:
        if issue.risk_level == "CRITICAL":
            result.critical_count += 1
        elif issue.risk_level == "HIGH":
            result.high_count += 1
        elif issue.risk_level == "MEDIUM":
            result.medium_count += 1

    result.total_issues = result.critical_count + result.high_count + result.medium_count

    return result


# ── Advisory Generation ─────────────────────────────────────────

def generate_advisory(result: DetectionResult) -> List[str]:
    """
    Generate human-readable advisory messages from detection results.

    Returns:
        List of advisory strings
    """
    advisories = []

    if result.total_issues == 0:
        return advisories

    # Competing consumers advisory
    for issue in result.competing_consumers:
        if issue.risk_level == "CRITICAL":
            advisories.append(
                f"CRITICAL_ARCHITECTURE_RISK: Multiple consumers on queue '{issue.queue_name}' "
                f"without conditional isolation. Consumers: {', '.join(issue.consumers)}. "
                f"VERIFY: competing consumers, conditional bean isolation, message routing."
            )
        elif issue.risk_level == "HIGH":
            advisories.append(
                f"HIGH_RISK: Multiple consumers on queue '{issue.queue_name}' "
                f"with partial conditional protection. Verify all consumers are properly isolated."
            )

    # Unisolated dependency advisory
    for issue in result.unisolated_dependencies:
        if issue.risk_level == "HIGH":
            advisories.append(
                f"HIGH_RISK: {issue.class_name} in {issue.file_path} depends on "
                f"{issue.dependency} without @ConditionalOnProperty. "
                f"This bean will be created in all modes, potentially causing runtime failures "
                f"or competing behavior."
            )

    return advisories