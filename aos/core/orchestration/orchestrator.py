"""Rule-driven team formation.

Ported from ``runtime/orchestrator/orchestrator.py``. Two things changed:

  * teams are built from **concrete roles** (``backend-architect``), not the
    router's abstract skill ids — that was the taxonomy break the old
    orchestrator carried;
  * the role catalog is the engine's ``registry/roles.json`` (content
    overridable) rather than a deleted markdown file.

Everything else — the R1-R10 selection rules and C1-C7 conflict rules — is
data in ``rules.json``, so no pattern is hardcoded here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from aos.config import get_paths
from aos.core.routing import taxonomy

_RULES_PATH = Path(__file__).resolve().parent / "rules.json"


# ── data types ─────────────────────────────────────────────────────────
@dataclass
class TeamPlan:
    """The outcome of team formation."""

    team_id: str
    lead_agent: str
    support_agents: list[str] = field(default_factory=list)
    is_multi_agent: bool = False
    reasoning: str = ""
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    pruned_roles: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── rule loading ───────────────────────────────────────────────────────
def _read_rules_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _content_rules_path() -> Path:
    return get_paths().policies_dir / "orchestration.json"


@lru_cache(maxsize=64)
def _cached_rules(content_path: Path) -> dict[str, Any]:
    """Merged rules, memoised by the content override path.

    ``_RULES_PATH`` is package data and never moves, so the content path
    alone identifies the effective rules. A file rewritten in place at the
    same path still needs :func:`reload`.
    """
    return _merge(_read_rules_file(_RULES_PATH), _read_rules_file(content_path))


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge one level deep, so an override can tune a single rule group."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def load_rules() -> dict[str, Any]:
    """Return the effective orchestration rules (content overrides built-in)."""
    return _cached_rules(_content_rules_path())


def reload() -> None:
    """Clear the rule cache (needed when a rules file is rewritten in place)."""
    _cached_rules.cache_clear()


# ── orchestration ──────────────────────────────────────────────────────
def should_form_team(
    *, domains: list[str], difficulty: str, intent: str, rules: Optional[dict[str, Any]] = None
) -> bool:
    """Decide whether a task warrants a team."""
    rules = rules or load_rules()
    activation = rules.get("activation_rules", {})
    if intent in activation.get("never_trigger_intents", []):
        return False
    if len(set(domains)) >= int(activation.get("domain_threshold", 2)):
        return True
    if activation.get("trigger_on_hard", True) and difficulty == "hard":
        return True
    if intent in activation.get("trigger_intents", []):
        return True
    return False


def form_team(
    task: str,
    *,
    lead_role: str,
    support_roles: Optional[list[str]] = None,
    domains: Optional[list[str]] = None,
    intent: str = "",
    difficulty: str = "medium",
    rules: Optional[dict[str, Any]] = None,
) -> TeamPlan:
    """Form a team from the routing decision, applying R1-R10 then C1-C7."""
    rules = rules or load_rules()
    team_rules = rules.get("team_rules", {})
    conflict_rules = rules.get("conflict_rules", {})
    catalog = taxonomy.role_catalog()
    domains = list(domains or [])
    applied: list[str] = []
    pruned: list[dict[str, Any]] = []
    team_id = f"team-{hashlib.md5(task.encode('utf-8')).hexdigest()[:8]}"

    if not should_form_team(domains=domains, difficulty=difficulty, intent=intent, rules=rules):
        return TeamPlan(
            team_id=team_id,
            lead_agent=lead_role,
            support_agents=[],
            is_multi_agent=False,
            reasoning="single-agent mode: activation rules not met",
            domains=domains,
            rules_applied=["activation: not triggered"],
        )

    lead = lead_role
    supports = [r for r in (support_roles or []) if r and r != lead]

    # R1: cross-domain augmentation.
    if team_rules.get("cross_domain_augment", True) and len(domains) > 1:
        for domain in domains[1:]:
            for role in _roles_for_domain(domain, catalog):
                if role != lead and role not in supports:
                    supports.append(role)
                    applied.append(f"R1: domain '{domain}' -> added {role}")

    # R2: architecture intent.
    if team_rules.get("architecture_include_system_architect", True) and intent == "architecture":
        if lead != "system-architect" and "system-architect" not in supports:
            supports.insert(0, "system-architect")
            applied.append("R2: architecture intent -> added system-architect")

    # R3: database domain.
    if team_rules.get("database_include_engineer", True) and "database" in domains:
        if lead != "database-engineer" and "database-engineer" not in supports:
            supports.append("database-engineer")
            applied.append("R3: database domain -> added database-engineer")

    # R4/R5: AI signals.
    task_lower = task.lower()
    if "ai" in domains:
        if any(kw in task_lower for kw in team_rules.get("retrieval_keywords", [])):
            if lead != "rag-engineer" and "rag-engineer" not in supports:
                supports.append("rag-engineer")
                applied.append("R4: AI + retrieval -> added rag-engineer")
        if any(kw in task_lower for kw in team_rules.get("llm_keywords", [])):
            if lead != "llm-engineer" and "llm-engineer" not in supports:
                supports.append("llm-engineer")
                applied.append("R5: AI + LLM -> added llm-engineer")

    # R6: distributed domain.
    if team_rules.get("distributed_include", True) and "distributed" in domains:
        if lead != "distributed-system" and "distributed-system" not in supports:
            supports.append("distributed-system")
            applied.append("R6: distributed domain -> added distributed-system")

    # R7: frontend domain.
    if team_rules.get("frontend_include_architect", True) and "frontend" in domains:
        if lead != "frontend-architect" and "frontend-architect" not in supports:
            supports.append("frontend-architect")
            applied.append("R7: frontend domain -> added frontend-architect")

    # R8: review roles only on explicit review intent.
    if team_rules.get("review_include", False) and intent == "review":
        for role in rules.get("intent_role_map", {}).get("review", []):
            if role != lead and role not in supports:
                supports.append(role)
                applied.append(f"R8: review intent -> added {role}")

    # R9: security domain or intent.
    if team_rules.get("security_include", True) and ("security" in domains or intent == "security"):
        if lead != "security-engineer" and "security-engineer" not in supports:
            supports.append("security-engineer")
            applied.append("R9: security -> added security-engineer")

    # R10: testing intent.
    if team_rules.get("testing_include", True) and intent == "testing":
        if lead != "testing-engineer" and "testing-engineer" not in supports:
            supports.append("testing-engineer")
            applied.append("R10: testing intent -> added testing-engineer")

    # C1: exactly one lead.
    applied.append(f"C1: lead = {lead}")

    # C2: prune roles not in the catalog.
    roles = [lead] + supports
    if conflict_rules.get("prune_unknown_roles", True):
        valid = []
        for role in roles:
            if role in catalog:
                valid.append(role)
            else:
                pruned.append({"role": role, "reason": "not_in_registry"})
                applied.append(f"C2: pruned {role} (not in registry)")
        roles = valid

    if not roles:
        return TeamPlan(
            team_id=team_id,
            lead_agent=lead,
            support_agents=[],
            is_multi_agent=False,
            reasoning="single-agent mode: no valid roles in registry",
            domains=domains,
            rules_applied=applied,
            pruned_roles=pruned,
        )

    # C5: team size cap.
    cap = int(conflict_rules.get("max_team_size", 7))
    if len(roles) > cap:
        for role in roles[cap:]:
            pruned.append({"role": role, "reason": "team_size_cap"})
            applied.append(f"C5: pruned {role} (team size cap)")
        roles = roles[:cap]

    lead_final = roles[0]
    supports_final = list(dict.fromkeys(roles[1:]))
    dependencies = _resolve_dependencies(lead_final, supports_final, catalog)

    return TeamPlan(
        team_id=team_id,
        lead_agent=lead_final,
        support_agents=supports_final,
        is_multi_agent=bool(supports_final),
        reasoning=_build_reasoning(domains, intent, difficulty, lead_final, supports_final),
        dependencies=dependencies,
        domains=domains,
        rules_applied=applied,
        pruned_roles=pruned,
    )


# ── helpers ────────────────────────────────────────────────────────────
def _roles_for_domain(domain: str, catalog: dict[str, dict]) -> list[str]:
    return [
        name
        for name, entry in catalog.items()
        if entry.get("domain") == domain and entry.get("status", "active") == "active"
    ]


def _resolve_dependencies(
    lead: str, supports: list[str], catalog: dict[str, dict]
) -> list[dict[str, Any]]:
    """Advisory ordering: keep only dependencies that are actually on the team."""
    all_roles = [lead] + supports
    dependencies = []
    for role in all_roles:
        entry = catalog.get(role, {})
        actual = [dep for dep in entry.get("dependencies", []) if dep in all_roles]
        if actual:
            dependencies.append({"role": role, "depends_on": actual})
    return dependencies


def _build_reasoning(
    domains: list[str], intent: str, difficulty: str, lead: str, supports: list[str]
) -> str:
    parts = [
        f"domains: {', '.join(domains) or 'none'}",
        f"intent: {intent}, difficulty: {difficulty}",
        f"lead: {lead}",
    ]
    if supports:
        parts.append(f"support: {', '.join(supports)}")
    return ". ".join(parts)
