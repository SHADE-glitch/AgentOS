#!/usr/bin/env python3
"""
Phase 8.2.1.1 — Memory Resolver & Bootstrap

Resolves memory IDs for candidates that target non-existent memory entries.
When a candidate references a memory ID not in the retrieval index, the resolver
auto-bootstraps a new Hypothesis (H-xxx) memory entry.

This closes GAP-1: P8-xxx memory IDs that don't exist in retrieval-index.yaml
are now auto-created as H-xxx hypotheses on first encounter.

Lifecycle:
  P8-xxx (collector generated)
    → resolver checks index
    → if not found: bootstrap H-xxx entry
    → candidate target_memory updated to H-xxx
    → validator treats H-xxx as hypothesis (M4 >=1)
    → promoter promotes H-xxx → elevates to P-xxx on second observation
"""

import os
import re
import yaml
import hashlib
from datetime import datetime, timezone
from typing import Optional

MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"
MEMORY_DIR = "/home/shade/.agents/memory"
HYPOTHESIS_DIR = os.path.join(MEMORY_DIR, "hypotheses")


def load_memory_index() -> dict:
    """Load the full retrieval-index."""
    if not os.path.exists(MEMORY_INDEX_FILE):
        return {"memories": []}
    with open(MEMORY_INDEX_FILE) as f:
        return yaml.safe_load(f) or {"memories": []}


def save_memory_index(index: dict):
    """Save the retrieval-index back to disk."""
    with open(MEMORY_INDEX_FILE, "w") as f:
        yaml.dump(index, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def memory_exists(memory_id: str) -> bool:
    """Check if a memory ID exists in the retrieval index."""
    index = load_memory_index()
    return any(m["memory_id"] == memory_id for m in index.get("memories", []))


def find_memory_entry(memory_id: str) -> Optional[dict]:
    """Find a memory entry in the retrieval index by ID."""
    index = load_memory_index()
    for m in index.get("memories", []):
        if m["memory_id"] == memory_id:
            return m
    return None


def bootstrap_hypothesis(pattern_name: str, source_loop_id: str,
                         source_team_id: str, agent_role: str,
                         lesson: str = "", context: str = "") -> str:
    """
    Bootstrap a new H-xxx hypothesis memory entry from a P8-xxx pattern.

    Creates:
      1. Memory metadata entry in retrieval-index.yaml
      2. .md file in memory/hypotheses/

    Returns:
        The H-xxx memory ID (e.g., H-001-CACHE-EXPIRATION)
    """
    # Generate a clean H-xxx ID
    clean = re.sub(r'[^a-zA-Z0-9]', '-', pattern_name).upper()
    if len(clean) > 30:
        clean = clean[:30]

    # Find next available H-xxx number
    index = load_memory_index()
    h_ids = [
        int(m["memory_id"].split("-")[1])
        for m in index.get("memories", [])
        if m["memory_id"].startswith("H-") and m["memory_id"].split("-")[1].isdigit()
    ]
    next_num = max(h_ids) + 1 if h_ids else 1
    memory_id = f"H-{next_num:03d}-{clean}"

    # Check if already bootstrapped (by pattern name)
    existing = find_memory_entry(memory_id)
    if existing:
        return memory_id

    # Phase 8.2.1.1: Check if same pattern was already bootstrapped under a different ID
    # This makes bootstrap idempotent across calls
    for m in index.get("memories", []):
        if m.get("type") == "hypothesis" and m.get("tags"):
            if clean.lower() in [t.lower() for t in m.get("tags", [])]:
                return m["memory_id"]

    # Create .md file
    os.makedirs(HYPOTHESIS_DIR, exist_ok=True)
    md_filename = f"{memory_id}.md"
    md_path = os.path.join(HYPOTHESIS_DIR, md_filename)

    md_content = f"""---
memory_id: {memory_id}
type: hypothesis
category: engineering_pattern
source_loop: {source_loop_id}
source_team: {source_team_id}
source_agent: {agent_role}
evidence_level: hypothesis
confidence: low
observation_count: 1
created_at: {datetime.now(timezone.utc).isoformat()}
tags:
  - auto-bootstrapped
  - {clean.lower()}
---

# {pattern_name}

## Pattern

{lesson[:500] if lesson else 'Auto-bootstrapped from multi-agent execution.'}

## Context

{context[:200] if context else 'First observed in multi-agent team execution.'}

## Source

- Loop: {source_loop_id}
- Team: {source_team_id}
- Agent: {agent_role}
- Bootstrapped: {datetime.now(timezone.utc).isoformat()}

## Status

This is an auto-bootstrapped hypothesis. It requires a second independent
observation before it can be elevated to a validated memory.
"""

    with open(md_path, "w") as f:
        f.write(md_content)

    # Add to retrieval-index
    new_entry = {
        "memory_id": memory_id,
        "file": f"memory/hypotheses/{md_filename}",
        "type": "hypothesis",
        "category": "engineering_pattern",
        "source_loop": source_loop_id,
        "source_team": source_team_id,
        "source_agent": agent_role,
        "evidence_level": "hypothesis",
        "confidence": "low",
        "observation_count": 1,
        "tags": ["auto-bootstrapped", clean.lower()],
        "status": "hypothesis",
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
    }

    index.setdefault("memories", []).append(new_entry)
    save_memory_index(index)

    return memory_id


def resolve_memory_id(target_memory: str, candidate: dict) -> str:
    """
    Resolve a target memory ID for a candidate.

    If the target_memory exists in the index, return it as-is.
    If it doesn't exist (e.g., P8-xxx), bootstrap a new H-xxx hypothesis.

    Args:
        target_memory: the original target memory ID (e.g., P8-CACHE-EXPIRATION)
        candidate: the candidate dict (for provenance)

    Returns:
        resolved memory ID (existing or newly bootstrapped)
    """
    # Already exists → no bootstrap needed
    if memory_exists(target_memory):
        return target_memory

    # NEW → special target that should be treated as create_hypothesis
    if target_memory == "NEW":
        return target_memory

    # P8-xxx or other unknown prefix → bootstrap
    # Extract pattern name from the ID
    pattern_name = target_memory.replace("P8-", "").replace("-", " ").title()

    source_loop = candidate.get("source_execution", "unknown")
    evidence = candidate.get("evidence", {})
    source_team = evidence.get("team_id", "unknown")
    agent_role = evidence.get("agent_role", "unknown")

    reasoning = candidate.get("reasoning", "")

    return bootstrap_hypothesis(
        pattern_name=pattern_name,
        source_loop_id=source_loop,
        source_team_id=source_team,
        agent_role=agent_role,
        lesson=reasoning[:500],
        context=pattern_name,
    )


def resolve_candidates_targets(candidates: list[dict]) -> list[dict]:
    """
    Resolve all candidate target_memory IDs.
    Modifies candidates in-place to use resolved (bootstrapped) IDs.

    Returns the modified candidates list.
    """
    for c in candidates:
        original = c["target_memory"]
        resolved = resolve_memory_id(original, c)
        if resolved != original:
            c["target_memory"] = resolved
            c["resolved_from"] = original
            c["candidate_id"] = c["candidate_id"].replace(original, resolved)
    return candidates