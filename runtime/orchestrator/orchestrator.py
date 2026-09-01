#!/usr/bin/env python3
"""
Orchestrator Runtime — Phase 7.3

Minimal team formation from Router DecisionContext.
Implements R1-R10 team selection rules and C1-C2 conflict rules.

Architecture:
  Task → Router.route() → DecisionContext → Orchestrator.form_team() → TeamPlan

This is the canonical Orchestrator Runtime. It replaces hardcoded team logic
in collaboration-protocol and agent-orchestrator skill.

Design constraints:
  - No AI models — pure rule engine
  - No external dependencies beyond PyYAML
  - Backward compatible with single-agent mode (no team for simple tasks)
  - All rules in rules.yaml — no hardcoded patterns in code
"""

import os
import re
import yaml
from typing import Optional

# Support both package import and standalone execution
try:
    from .team import TeamPlan, RoleEntry, load_role_registry
except ImportError:
    from team import TeamPlan, RoleEntry, load_role_registry

try:
    from ..router.decision import DecisionContext
except ImportError:
    import sys
    _router_dir = os.path.join(os.path.dirname(__file__), "..", "router")
    if _router_dir not in sys.path:
        sys.path.insert(0, _router_dir)
    from decision import DecisionContext

BASE = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
DEFAULT_RULES_PATH = os.path.join(BASE, "runtime", "orchestrator", "rules.yaml")


class Orchestrator:
    """
    Rule-driven team orchestrator.

    Usage:
        orch = Orchestrator()
        orch.load_rules()
        team = orch.form_team(task, decision_context)
    """

    def __init__(self, rules_path: str = None):
        self.rules_path = rules_path or DEFAULT_RULES_PATH
        self.role_registry: dict = {}  # {name: RoleEntry}
        self.team_rules: dict = {}     # from rules.yaml
        self.activation_rules: dict = {}
        self._loaded = False

    def load_rules(self) -> None:
        """Load orchestrator rules from rules.yaml."""
        with open(self.rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        self.team_rules = rules.get("team_rules", {})
        self.activation_rules = rules.get("activation_rules", {})
        self.role_registry = load_role_registry()
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_rules()

    # ── Activation Check ──────────────────────────────────────────

    def should_form_team(self, decision: DecisionContext) -> bool:
        """
        Check activation conditions per SKILL.md Section 4.

        Activate when:
        - domain >= 2 (cross-domain task)
        - difficulty == "hard" (complex task)
        - intent == "architecture" (system-level design)
        """
        domain_count = len(decision.domains)
        if domain_count >= 2:
            return True
        if decision.difficulty == "hard":
            return True
        if decision.intent == "architecture":
            return True
        return False

    # ── Team Formation (R1-R10) ──────────────────────────────────

    def form_team(self, task: str, decision: DecisionContext) -> TeamPlan:
        """
        Form a team from Router DecisionContext.

        Pipeline:
          1. Determine if team is needed (activation)
          2. Select baseline team from decision + domain mapping
          3. Apply R1-R10 team selection rules
          4. Apply C1-C2 conflict rules
          5. Build TeamPlan
        """
        self._ensure_loaded()

        team_id = self._generate_team_id(task)
        rules_applied = []
        pruned_roles = []

        # Baseline: use router's lead + support
        lead = decision.lead_skill
        supports = [s for s in decision.support_skills if s != lead]

        # R1: Domain-based augmentation
        # If multiple domains, add roles from additional domains
        if len(decision.domains) > 1:
            for domain in decision.domains[1:]:
                domain_roles = self._roles_for_domain(domain)
                for role in domain_roles:
                    if role != lead and role not in supports:
                        if len(supports) < 6:  # C5: cap at 7 total (lead + 6 support)
                            supports.append(role)
                            rules_applied.append(f"R1: domain '{domain}' → added {role}")

        # R2: Architecture/system-level → system-architect
        if decision.intent == "architecture" and lead != "system-architect":
            if "system-architect" not in supports:
                supports.insert(0, "system-architect")
                rules_applied.append("R2: architecture intent → added system-architect")

        # R3: Database domain → database-engineer
        if "database" in decision.domains:
            if "database-engineer" not in supports and lead != "database-engineer":
                supports.append("database-engineer")
                rules_applied.append("R3: database domain → added database-engineer")

        # R4: AI + retrieval → rag-engineer
        if "ai" in decision.domains:
            task_lower = task.lower()
            if any(kw in task_lower for kw in ["rag", "retrieval", "vector", "检索", "向量"]):
                if "rag-engineer" not in supports and lead != "rag-engineer":
                    supports.append("rag-engineer")
                    rules_applied.append("R4: AI + retrieval → added rag-engineer")

        # R5: AI + LLM → llm-engineer
        if "ai" in decision.domains:
            task_lower = task.lower()
            if any(kw in task_lower for kw in ["llm", "大模型", "model", "模型"]):
                if "llm-engineer" not in supports and lead != "llm-engineer":
                    supports.append("llm-engineer")
                    rules_applied.append("R5: AI + LLM → added llm-engineer")

        # R6: Performance/concurrency → distributed-system
        if any(d in decision.domains for d in ["distributed"]):
            if "distributed-system" not in supports and lead != "distributed-system":
                supports.append("distributed-system")
                rules_applied.append("R6: distributed domain → added distributed-system")

        # R7: Frontend domain → frontend-architect
        if "frontend" in decision.domains:
            if "frontend-architect" not in supports and lead != "frontend-architect":
                supports.append("frontend-architect")
                rules_applied.append("R7: frontend domain → added frontend-architect")

        # R9: Security domain/intent → security-engineer
        if "security" in decision.domains or decision.intent == "security":
            if "security-engineer" not in supports and lead != "security-engineer":
                supports.append("security-engineer")
                rules_applied.append("R9: security → added security-engineer")

        # R10: Testing intent → testing-engineer
        if decision.intent == "testing":
            if "testing-engineer" not in supports and lead != "testing-engineer":
                supports.append("testing-engineer")
                rules_applied.append("R10: testing intent → added testing-engineer")

        # ── Conflict Rules ────────────────────────────────────────

        # C1: Exactly one lead — lead is already set from router
        rules_applied.append(f"C1: lead = {lead}")

        # C2: Prune roles not in registry
        all_roles = [lead] + supports
        valid_roles = []
        for role in all_roles:
            if role in self.role_registry:
                valid_roles.append(role)
            else:
                pruned_roles.append({"role": role, "reason": "not_in_registry"})
                rules_applied.append(f"C2: pruned {role} (not in registry)")

        if not valid_roles:
            # Fallback: single agent
            return TeamPlan(
                team_id=team_id,
                lead_agent=lead,
                support_agents=[],
                reasoning="Single-agent mode: no valid multi-role team",
                domains=decision.domains,
                rules_applied=rules_applied,
                pruned_roles=pruned_roles,
            )

        # C5: Team size cap at 7
        if len(valid_roles) > 7:
            pruned = valid_roles[7:]
            valid_roles = valid_roles[:7]
            for role in pruned:
                pruned_roles.append({"role": role, "reason": "team_size_cap"})
                rules_applied.append(f"C5: pruned {role} (team size cap)")

        # Deduplicate supports
        lead_final = valid_roles[0]
        supports_final = list(dict.fromkeys(valid_roles[1:]))

        # Build dependencies
        dependencies = self._resolve_dependencies(lead_final, supports_final)

        # Build reasoning
        reasoning = self._build_reasoning(
            decision, lead_final, supports_final, rules_applied
        )

        return TeamPlan(
            team_id=team_id,
            lead_agent=lead_final,
            support_agents=supports_final,
            reasoning=reasoning,
            dependencies=dependencies,
            domains=decision.domains,
            rules_applied=rules_applied,
            pruned_roles=pruned_roles,
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _generate_team_id(self, task: str) -> str:
        """Generate a deterministic team ID from task text."""
        import hashlib
        task_hash = hashlib.md5(task.encode()).hexdigest()[:8]
        return f"team-{task_hash}"

    def _roles_for_domain(self, domain: str) -> list:
        """Get role names belonging to a domain from the registry."""
        return [
            name for name, entry in self.role_registry.items()
            if entry.domain == domain and entry.status == "active"
        ]

    def _resolve_dependencies(self, lead: str, supports: list) -> list:
        """
        Resolve dependency ordering from role registry.

        Returns list of {role: ..., depends_on: [...]} dicts.
        """
        all_roles = [lead] + supports
        deps = []
        for role in all_roles:
            entry = self.role_registry.get(role)
            if entry and entry.dependencies:
                # Only include deps that are in the team
                actual_deps = [d for d in entry.dependencies if d in all_roles]
                if actual_deps:
                    deps.append({"role": role, "depends_on": actual_deps})
        return deps

    def _build_reasoning(
        self, decision: DecisionContext, lead: str, supports: list, rules: list
    ) -> str:
        """Build human-readable reasoning for team selection."""
        parts = [
            f"Task domains: {', '.join(decision.domains)}",
            f"Intent: {decision.intent}, Difficulty: {decision.difficulty}",
            f"Lead: {lead}",
        ]
        if supports:
            parts.append(f"Support: {', '.join(supports)}")
        if rules:
            parts.append(f"Rules applied: {'; '.join(rules)}")
        return ". ".join(parts)


# ── Module-level function ────────────────────────────────────────

_orchestrator_instance: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get or create the singleton Orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = Orchestrator()
        _orchestrator_instance.load_rules()
    return _orchestrator_instance


def form_team(task: str, decision: DecisionContext) -> TeamPlan:
    """
    Convenience function: form a team from task + decision context.

    Usage:
        from runtime.orchestrator import form_team
        from runtime.router import get_router

        router = get_router()
        decision = router.route("设计一个高并发秒杀系统")
        team = form_team(decision.task_text, decision)
    """
    orch = get_orchestrator()
    return orch.form_team(task, decision)


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "router"))
    from router import Router

    if len(sys.argv) < 2:
        print("Usage: python3 orchestrator.py <task_text>")
        print("Example: python3 orchestrator.py '设计一个高并发秒杀系统'")
        sys.exit(1)

    task_text = sys.argv[1]
    router = Router()
    router.load_rules()
    decision = router.route(task_text)

    print("=" * 60)
    print("Router Decision")
    print("=" * 60)
    print(f"  Lead:       {decision.lead_skill}")
    print(f"  Support:    {decision.support_skills}")
    print(f"  Domains:    {decision.domains}")
    print(f"  Confidence: {decision.confidence}")

    team = form_team(task_text, decision)

    print()
    print("=" * 60)
    print("Team Plan")
    print("=" * 60)
    print(f"  Team ID:    {team.team_id}")
    print(f"  Lead:       {team.lead_agent}")
    print(f"  Support:    {team.support_agents}")
    print(f"  Domains:    {team.domains}")
    print(f"  Rules:      {team.rules_applied}")
    print(f"  Pruned:     {team.pruned_roles}")
    print(f"  Reasoning:  {team.reasoning}")
