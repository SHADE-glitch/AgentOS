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
    confidence_numeric: float = 0.5  # Phase13.1 numeric 0-1
    fallback_reason: str = None  # Phase13.1: unknown_domain | low_confidence | conflicting_intent | multi_domain

    # Candidate ranking (Phase13.1)
    candidates: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)

    # Phase14 Hybrid Router additions (backward compatible — defaults keep
    # legacy callers working; consumers that don't read these fields are
    # unaffected because they default to None/empty)
    route_mode: str = "lexical"  # "lexical" | "semantic" | "planner"
    escalation_reason: str = None  # domain_unrecognized | partial_known | ambiguous | low_separation | low_confidence | None
    semantic_features: dict = field(default_factory=dict)  # intent_core, entities, action, domain_signal, lure_terms, contradiction

    # Memory influence
    memory_influence: str = "none"  # "none" | "weak" | "confirmation" | "conflict"
    memory_retrieved: int = 0

    # Provenance
    rules_applied: list = field(default_factory=list)
    router_version: str = "2.0"

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
            "confidence_numeric": self.confidence_numeric,
            "fallback_reason": self.fallback_reason,
            "candidates": self.candidates,
            "scores": self.scores,
            "route_mode": self.route_mode,
            "escalation_reason": self.escalation_reason,
            "semantic_features": self.semantic_features,
            "difficulty": self.difficulty,
            "memory_influence": self.memory_influence,
            "memory_retrieved": self.memory_retrieved,
            "rules_applied": self.rules_applied,
            "router_version": self.router_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def to_artifact(self) -> dict:
        """Phase14 router decision artifact (extends Phase13.1; legacy keys preserved).

        Backward compatibility: ``confidence`` stays the legacy label string so
        existing consumers (loop_controller/agent_router) keep working. The
        numeric 0..1 value is carried in ``confidence_numeric`` (Phase13.1) and
        the new Phase14 manifest builder re-exposes it under ``confidence`` for
        the benchmark judge.
        """
        return {
            "task": self.task_text,
            "candidates": self.candidates,
            "scores": self.scores,
            "confidence": self.confidence,
            "confidence_numeric": self.confidence_numeric,
            "selected": self.lead_skill,
            "support_skills": self.support_skills,
            "fallback_reason": self.fallback_reason,
            "route_mode": self.route_mode,
            "escalation_reason": self.escalation_reason,
            "semantic_features": self.semantic_features,
            "intent": self.intent,
            "domains": self.domains,
            "primary_domain": self.primary_domain,
            "rules_applied": self.rules_applied,
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