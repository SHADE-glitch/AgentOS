"""
Decision Context — Phase 7.1

Standardized routing decision output from the Router.
Used by loop_controller, runtime_adapter, and trace builder.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DecisionContext:
    """Complete routing decision produced by Router.route()."""

    # Task identity
    task_text: str

    # Intent classification
    intent: str = "coding"

    # Domain classification
    domains: list = field(default_factory=lambda: ["backend"])
    primary_domain: str = "backend"

    # Skill selection
    lead_skill: str = "backend-architect"
    support_skills: list = field(default_factory=list)

    # Confidence
    confidence: str = "medium"  # "high" | "medium" | "low"
    difficulty: str = "medium"  # "easy" | "medium" | "hard"

    # Memory influence
    memory_influence: str = "none"  # "none" | "weak" | "confirmation" | "conflict"
    memory_retrieved: int = 0

    # Provenance
    rules_applied: list = field(default_factory=list)
    router_version: str = "1.0"

    # Timestamps
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for serialization (YAML-safe)."""
        return asdict(self)

    def to_trace_dict(self) -> dict:
        """Convert to the trace format expected by runtime_adapter.build_trace()."""
        return {
            "intent": self.intent,
            "domains": self.domains,
            "primary_domain": self.primary_domain,
            "lead_skill": self.lead_skill,
            "support_skills": self.support_skills,
            "confidence": self.confidence,
            "difficulty": self.difficulty,
            "memory_influence": self.memory_influence,
            "memory_retrieved": self.memory_retrieved,
            "rules_applied": self.rules_applied,
            "router_version": self.router_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class ClassificationResult:
    """Lightweight classification result (for retrieval adapter compatibility)."""

    task_text: str
    category: str = "backend"
    domains: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    difficulty: str = "medium"

    def to_dict(self) -> dict:
        return asdict(self)