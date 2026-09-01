"""
Team Plan and Role Registry — Phase 7.3

Defines TeamPlan dataclass and role registry loading from role-registry.md.
"""

import os
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RoleEntry:
    """A single role from the role registry."""
    name: str
    domain: str
    responsibility: str
    dependencies: list = field(default_factory=list)
    consumers: list = field(default_factory=list)
    activation_keywords: list = field(default_factory=list)
    status: str = "active"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TeamPlan:
    """Output of Orchestrator.form_team() — a minimal team plan."""
    team_id: str
    lead_agent: str
    support_agents: list = field(default_factory=list)
    reasoning: str = ""
    dependencies: list = field(default_factory=list)
    domains: list = field(default_factory=list)
    rules_applied: list = field(default_factory=list)
    pruned_roles: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


BASE = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
DEFAULT_ROLE_REGISTRY = os.path.join(
    BASE, "skills", "meta", "role-registry.md"
)


def load_role_registry(path: str = None) -> dict:
    """
    Parse role-registry.md and return {role_name: RoleEntry}.

    The file uses markdown blocks with YAML-like fields inside ```yaml blocks.
    Each role block has: name, domain, responsibility, input, output,
    dependencies, consumers, activation_keywords, status.
    """
    path = path or DEFAULT_ROLE_REGISTRY
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    roles = {}
    # Split on ```yaml blocks containing role definitions
    blocks = re.split(r"```yaml\s*\nrole:\n", content)

    for block in blocks[1:]:  # skip preamble
        name = _extract_field(block, "name")
        if not name or name.startswith("<"):
            continue  # skip documentation blocks with placeholder values
        domain = _extract_field(block, "domain", "backend")
        if domain.startswith("<"):
            continue
        responsibility = _extract_field(block, "responsibility", "")
        dependencies = _extract_list_field(block, "dependencies")
        consumers = _extract_list_field(block, "consumers")
        activation_keywords = _extract_list_field(block, "activation_keywords")
        status = _extract_field(block, "status", "active")

        roles[name] = RoleEntry(
            name=name,
            domain=domain,
            responsibility=responsibility,
            dependencies=dependencies,
            consumers=consumers,
            activation_keywords=activation_keywords,
            status=status,
        )

    return roles


def _extract_field(block: str, field_name: str, default: str = "") -> str:
    """Extract a single YAML-like field value from a markdown block."""
    pattern = rf"^\s*{field_name}:\s*(.+)$"
    match = re.search(pattern, block, re.MULTILINE)
    if match:
        val = match.group(1).strip().strip('"').strip("'")
        return val
    return default


def _extract_list_field(block: str, field_name: str) -> list:
    """Extract a YAML list field from a markdown block."""
    # Handle inline list: [a, b, c]
    inline_pattern = rf"^\s*{field_name}:\s*\[(.+)\]"
    match = re.search(inline_pattern, block, re.MULTILINE)
    if match:
        items = match.group(1).split(",")
        return [item.strip().strip('"').strip("'") for item in items if item.strip()]

    # Handle block list: - item
    block_pattern = rf"^\s*{field_name}:\s*\n((?:\s*-\s*.+\n?)+)"
    match = re.search(block_pattern, block, re.MULTILINE)
    if match:
        lines = match.group(1).strip().split("\n")
        return [re.sub(r"^\s*-\s*", "", line).strip() for line in lines if line.strip()]

    return []
