#!/usr/bin/env python3
"""
Skill Loader — Phase 5.7

Loads SKILL.md files from the skills directory and builds execution context.
This is NOT a simulation. It reads actual SKILL.md files and produces
a SkillContext that the Runtime Adapter uses to construct prompts.

Skill boundary:
  - Skill = professional execution context (prompt prefix, role, constraints)
  - Runtime = actual execution carrier (OpenCode CLI, TestProvider)

The Skill Loader does NOT execute anything. It only provides context.
"""

import os
import re
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
SKILLS_DIR = os.path.join(BASE, "skills")


def list_available_skills() -> list:
    """List all available skill names from the skills directory."""
    skills = []
    if not os.path.isdir(SKILLS_DIR):
        return skills

    for root, dirs, files in os.walk(SKILLS_DIR):
        if "SKILL.md" in files:
            skill_name = os.path.basename(root)
            # Skip meta skills (they are internal)
            if skill_name in ("meta", "version-history"):
                continue
            skills.append(skill_name)

    return sorted(set(skills))


def load_skill(skill_name: str) -> dict:
    """
    Load a SKILL.md file and parse it into a SkillContext.

    Args:
        skill_name: e.g., "backend-architect", "rag-engineer"

    Returns:
        dict: SkillContext with name, description, mission, expertise, activation
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # Find the SKILL.md file
    skill_path = None
    for root, dirs, files in os.walk(SKILLS_DIR):
        if os.path.basename(root) == skill_name and "SKILL.md" in files:
            skill_path = os.path.join(root, "SKILL.md")
            break

    if skill_path is None:
        # Try with category prefix
        for root, dirs, files in os.walk(SKILLS_DIR):
            if os.path.basename(root) == skill_name and "SKILL.md" in files:
                skill_path = os.path.join(root, "SKILL.md")
                break

    if skill_path is None:
        return {
            "name": skill_name,
            "loaded": False,
            "error": f"SKILL.md not found for: {skill_name}",
            "description": "",
            "mission": "",
            "expertise": [],
            "activation": "",
            "content": "",
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    # Read and parse SKILL.md
    with open(skill_path) as f:
        content = f.read()

    # Parse frontmatter if present
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    key, val = line.split(":", 1)
                    frontmatter[key.strip()] = val.strip()
            body = parts[2].strip()

    # Extract sections
    name = frontmatter.get("name", skill_name)
    description = frontmatter.get("description", "")
    mission = _extract_section(body, "Mission")
    expertise = _extract_list_section(body, "Expertise")
    activation = _extract_section(body, "Activation Rules")

    completed_at = datetime.now(timezone.utc).isoformat()

    return {
        "name": name,
        "loaded": True,
        "skill_path": skill_path,
        "description": description,
        "mission": mission,
        "expertise": expertise,
        "activation": activation,
        "content": body,
        "started_at": started_at,
        "completed_at": completed_at,
    }


def build_skill_context(route_decision: dict) -> dict:
    """
    Build a SkillContext from a RouteDecision.

    Loads the lead skill and support skills, then constructs
    a prompt prefix that the Runtime Adapter can inject.

    Args:
        route_decision: dict from agent_router.route()

    Returns:
        dict: SkillContext with prompt_prefix, skills_loaded, etc.
    """
    started_at = datetime.now(timezone.utc).isoformat()

    lead_skill_name = route_decision.get("lead_skill", "backend-architect")
    support_skill_names = route_decision.get("support_skills", [])

    # Load lead skill
    lead_skill = load_skill(lead_skill_name)

    # Load support skills
    support_skills = []
    for name in support_skill_names:
        skill = load_skill(name)
        if skill["loaded"]:
            support_skills.append(skill)

    # Build prompt prefix
    prompt_prefix = _build_prompt_prefix(lead_skill, support_skills, route_decision)

    completed_at = datetime.now(timezone.utc).isoformat()

    return {
        "lead_skill": lead_skill,
        "support_skills": support_skills,
        "skills_loaded": [lead_skill["name"]] + [s["name"] for s in support_skills],
        "prompt_prefix": prompt_prefix,
        "started_at": started_at,
        "completed_at": completed_at,
    }


def _build_prompt_prefix(lead_skill: dict, support_skills: list, route_decision: dict) -> str:
    """Build a prompt prefix from skill context."""
    parts = []

    # Role assignment
    lead_name = lead_skill.get("name", "engineer")
    display_name = lead_name.replace("-", " ").title()
    parts.append(f"You are acting as a **{display_name}**.")

    if lead_skill.get("loaded"):
        if lead_skill.get("mission"):
            parts.append(f"Mission: {lead_skill['mission']}")
        if lead_skill.get("description"):
            parts.append(f"Role: {lead_skill['description']}")

    if support_skills:
        support_names = [s["name"].replace("-", " ").title() for s in support_skills if s.get("loaded")]
        if support_names:
            parts.append(f"Support skills available: {', '.join(support_names)}")

    parts.append("")

    # Domain context
    domains = route_decision.get("domains", [])
    if domains:
        parts.append(f"Domain: {', '.join(domains)}")

    intent = route_decision.get("intent", "coding")
    parts.append(f"Task type: {intent}")

    return "\n".join(parts)


def _extract_section(content: str, heading: str) -> str:
    """Extract a section's content by heading."""
    pattern = rf"##\s+\d+\.\s+{heading}\s*\n(.*?)(?=##\s+\d+\.|$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_list_section(content: str, heading: str) -> list:
    """Extract a list section by heading."""
    section = _extract_section(content, heading)
    items = []
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:])
    return items