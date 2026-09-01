#!/usr/bin/env python3
"""
Standalone Agent Router — Phase 7.1

Rule-driven task router that classifies intent, maps domains,
and selects lead/support skills. Loads rules from rules.yaml.

Architecture:
  Task Input → Router.classify() → ClassificationResult
  Task Input → Router.route() → DecisionContext
  Router.route() = classify() + skill_mapping() + confidence() + memory_influence()

This is the canonical Router Runtime. It replaces the hardcoded regex
classification in retrieval_adapter.py and agent_router.py.

Design constraints:
  - No AI models — pure rule engine
  - No external dependencies beyond PyYAML
  - Backward compatible with agent_router.route() and retrieval_adapter.classify_task()
  - All rules in rules.yaml — no hardcoded patterns in code
"""

import os
import re
import sys
import yaml
from datetime import datetime, timezone
from typing import Optional

# Support both package import (from runtime.router) and standalone execution
try:
    from .decision import DecisionContext, ClassificationResult
except ImportError:
    from decision import DecisionContext, ClassificationResult

BASE = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
DEFAULT_RULES_PATH = os.path.join(BASE, "runtime", "router", "rules.yaml")


class Router:
    """
    Rule-driven task router.

    Usage:
        router = Router()
        router.load_rules()

        # Full routing
        decision = router.route("分析 MySQL 慢查询问题")

        # Lightweight classification (for retrieval adapter)
        classification = router.classify("分析 MySQL 慢查询问题")
    """

    def __init__(self, rules_path: str = None):
        self.rules_path = rules_path or DEFAULT_RULES_PATH
        self.intent_rules: list = []
        self.domain_rules: list = []
        self.skill_category_map: dict = {}
        self.intent_skill_priority: dict = {}
        self.difficulty_rules: list = []
        self.keyword_rules: list = []
        self.role_rules: list = []
        self.fallback: dict = {}
        self.confidence_config: dict = {}

        # Compiled regex cache
        self._intent_patterns: list = []
        self._domain_patterns: list = []
        self._difficulty_patterns: list = []
        self._keyword_patterns: list = []
        self._role_patterns: list = []

        self._loaded = False

    # ── Rule Loading ──────────────────────────────────────────────

    def load_rules(self) -> None:
        """Load routing rules from rules.yaml and compile regex patterns."""
        with open(self.rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)

        self._rules_data = rules  # keep raw dict for runtime access

        self.intent_rules = rules.get("intent_rules", [])
        self.domain_rules = rules.get("domain_rules", [])
        self.skill_category_map = rules.get("skill_category_map", {})
        self.intent_skill_priority = rules.get("intent_skill_priority", {})
        self.difficulty_rules = rules.get("difficulty_rules", [])
        self.keyword_rules = rules.get("keyword_rules", [])
        self.role_rules = rules.get("role_rules", [])
        self.fallback = rules.get("fallback", {})
        self.confidence_config = rules.get("confidence", {})

        # Compile regex patterns
        self._compile_patterns()
        self._loaded = True

    def _compile_patterns(self) -> None:
        """Pre-compile all regex patterns for performance."""
        self._intent_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.intent_rules
        ]
        self._domain_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.domain_rules
        ]
        self._difficulty_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.difficulty_rules
        ]
        self._keyword_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.keyword_rules
        ]
        self._role_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.role_rules
        ]

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_rules()

    # ── Classification ────────────────────────────────────────────

    def classify(self, task_text: str) -> ClassificationResult:
        """
        Lightweight classification: intent, domains, roles, keywords, difficulty.

        Returns ClassificationResult — compatible with retrieval_adapter.classify_task().
        """
        self._ensure_loaded()

        # Intent (first match)
        intent = self.fallback.get("default_intent", "coding")
        for name, pattern in self._intent_patterns:
            if pattern.search(task_text):
                intent = name
                break

        # Domain (all matches)
        domains = []
        for name, pattern in self._domain_patterns:
            if pattern.search(task_text):
                domains.append(name)
        if not domains:
            domains = [self.fallback.get("default_domain", "backend")]

        # Roles (all matches)
        roles = []
        for name, pattern in self._role_patterns:
            if pattern.search(task_text):
                roles.append(name)

        # Keywords (all matches)
        keywords = []
        for name, pattern in self._keyword_patterns:
            if pattern.search(task_text):
                keywords.append(name)

        # Difficulty (first match)
        difficulty = self.fallback.get("default_difficulty", "medium")
        for name, pattern in self._difficulty_patterns:
            if pattern.search(task_text):
                difficulty = name
                break

        return ClassificationResult(
            task_text=task_text,
            category=intent,  # "category" = intent for backward compat
            domains=domains,
            roles=roles,
            keywords=keywords,
            difficulty=difficulty,
        )

    # ── Full Routing ──────────────────────────────────────────────

    def route(self, task_text: str, memory_context: dict = None) -> DecisionContext:
        """
        Full routing pipeline: classify → skill mapping → confidence → memory influence.

        Domain-first approach: the primary domain determines the lead skill.
        Intent modifies selection within the domain (e.g., review intent → reviewer).

        Args:
            task_text: The task description
            memory_context: Optional dict with 'memories' key for memory influence

        Returns:
            DecisionContext with complete routing decision
        """
        self._ensure_loaded()
        started_at = datetime.now(timezone.utc).isoformat()

        # Stage 1: Classification
        classification = self.classify(task_text)
        intent = classification.category
        domains = classification.domains
        primary_domain = domains[0]

        # Stage 2: Skill mapping (DOMAIN-FIRST)
        lead_skill = None
        support_skills = []
        rules_applied = []

        # Domain skills are the primary candidates
        domain_skills = self.skill_category_map.get(primary_domain, [])

        # Intent-based modifiers for specific intents
        if intent == "review":
            # Review intent: "评审" explicitly signals a review task
            # Use review candidates directly, not domain skills
            review_candidates = self.intent_skill_priority.get(
                intent, ["system-architect", "technical-reviewer", "code-reviewer"]
            )
            lead_skill = self._select_lead_from_domain(review_candidates, task_text)
            for skill in review_candidates:
                if skill != lead_skill and len(support_skills) < 2:
                    support_skills.append(skill)
            rules_applied.append(f"Review intent → {lead_skill}")

        elif intent == "security":
            lead_skill = "security-engineer"
            rules_applied.append("Security intent → security-engineer")

        elif intent == "learning":
            # Learning intent: select learning roles using keyword hints
            priority = self.intent_skill_priority.get(intent, [])
            if priority:
                lead_skill = self._select_lead_from_domain(priority, task_text)
                for skill in priority:
                    if skill != lead_skill and len(support_skills) < 2:
                        support_skills.append(skill)
            else:
                lead_skill = "learning-strategist"
            rules_applied.append(f"Learning intent → {lead_skill}")

        elif domain_skills:
            # Domain-first: lead = first domain skill, refined by keyword hints
            lead_skill = self._select_lead_from_domain(domain_skills, task_text)
            rules_applied.append(f"Domain '{primary_domain}' → lead {lead_skill}")

            # Add remaining domain skills as support (up to 2)
            for skill in domain_skills:
                if skill != lead_skill and len(support_skills) < 2:
                    support_skills.append(skill)

        # Fallback: intent-based priority
        if lead_skill is None:
            priority = self.intent_skill_priority.get(intent, [])
            if priority:
                lead_skill = priority[0]
                for skill in priority[1:3]:
                    if skill != lead_skill and len(support_skills) < 2:
                        support_skills.append(skill)
                rules_applied.append(f"Intent '{intent}' → {lead_skill}")
            else:
                lead_skill = self.fallback.get("default_lead_skill", "backend-architect")
                rules_applied.append("Fallback: no match → default lead")

        # Augment support from intent priorities (if not already added)
        priority_skills = self.intent_skill_priority.get(intent, [])
        for skill in priority_skills:
            if skill != lead_skill and skill not in support_skills:
                if len(support_skills) < 3:
                    support_skills.append(skill)

        # Stage 3: Confidence
        confidence = self._assess_confidence(domains, primary_domain)

        # Stage 4: Memory influence
        memory_influence = "none"
        memory_count = 0
        if memory_context:
            memories = memory_context.get("memories", [])
            memory_count = len(memories)
            if memory_count >= 3:
                memory_influence = "confirmation"
            elif memory_count >= 1:
                memory_influence = "weak"

        completed_at = datetime.now(timezone.utc).isoformat()

        return DecisionContext(
            task_text=task_text,
            intent=intent,
            domains=domains,
            primary_domain=primary_domain,
            lead_skill=lead_skill,
            support_skills=support_skills,
            confidence=confidence,
            difficulty=classification.difficulty,
            memory_influence=memory_influence,
            memory_retrieved=memory_count,
            rules_applied=rules_applied,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _assess_confidence(self, domains: list, primary_domain: str) -> str:
        """Heuristic confidence assessment based on domain match count."""
        if len(domains) == 1 and primary_domain in self.skill_category_map:
            return "high"
        elif len(domains) >= 3:
            return "low"
        return "medium"

    def _select_lead_from_domain(self, domain_skills: list, task_text: str) -> str:
        """
        Select the best lead skill from domain skills using keyword hints.

        If the task text contains keywords for a specific skill, prefer that skill.
        Otherwise, use the first domain skill as default.
        """
        if not domain_skills:
            return self.fallback.get("default_lead_skill", "backend-architect")

        if len(domain_skills) == 1:
            return domain_skills[0]

        hints = self._rules_data.get("skill_keyword_hints", {})
        if not hints:
            return domain_skills[0]

        # Score each domain skill by how many of its keywords match the task
        best_skill = domain_skills[0]
        best_score = 0
        for skill in domain_skills:
            skill_hints = hints.get(skill, [])
            score = sum(
                1 for kw in skill_hints
                if re.search(re.escape(kw), task_text, re.I)
            )
            if score > best_score:
                best_score = score
                best_skill = skill

        return best_skill


# ── Singleton ─────────────────────────────────────────────────────

_router_instance: Optional[Router] = None


def get_router() -> Router:
    """Get or create the singleton Router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = Router()
        _router_instance.load_rules()
    return _router_instance


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 router.py <task_text>")
        print("Example: python3 router.py '分析 MySQL 慢查询问题'")
        sys.exit(1)

    task_text = sys.argv[1]
    router = Router()
    router.load_rules()

    print("=" * 60)
    print("Classification")
    print("=" * 60)
    c = router.classify(task_text)
    print(f"  Intent:    {c.category}")
    print(f"  Domains:   {c.domains}")
    print(f"  Roles:     {c.roles}")
    print(f"  Keywords:  {c.keywords}")
    print(f"  Difficulty: {c.difficulty}")

    print()
    print("=" * 60)
    print("Route Decision")
    print("=" * 60)
    d = router.route(task_text)
    print(f"  Lead:      {d.lead_skill}")
    print(f"  Support:   {d.support_skills}")
    print(f"  Confidence: {d.confidence}")
    print(f"  Mem Infl:  {d.memory_influence}")
    print(f"  Rules:     {d.rules_applied}")