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
OBSERVATION_LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "memory-observation-log.yaml"
)


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


def _infer_domain_metadata(pattern_name: str) -> dict:
    """
    Infer domain, category, and technical tags from a pattern name.
    Maps pattern name keywords to retrieval-compatible domain/category/tag values.

    This ensures H-xxx hypotheses can be matched by the retrieval optimizer's
    domain_match and keyword_match scoring dimensions.

    Returns:
        dict with keys: domain, category, technical_tags
    """
    name_lower = pattern_name.lower()

    # ── Domain inference ──────────────────────────────────────
    domain = "backend"  # default
    if any(kw in name_lower for kw in ["redis", "database", "sql", "schema", "db", "transaction"]):
        domain = "database"
    elif any(kw in name_lower for kw in ["test", "testing", "assert", "mock"]):
        domain = "testing"
    elif any(kw in name_lower for kw in ["rag", "llm", "embedding", "vector", "prompt", "ai", "model"]):
        domain = "ai"
    elif any(kw in name_lower for kw in ["frontend", "vue", "react", "ui", "component"]):
        domain = "frontend"
    elif any(kw in name_lower for kw in ["security", "auth", "token", "permission", "rbac"]):
        domain = "security"

    # ── Category inference ────────────────────────────────────
    category = "engineering_pattern"
    if any(kw in name_lower for kw in ["bug", "defect", "race", "leak", "deadlock", "corruption"]):
        category = "bug_pattern"
    elif any(kw in name_lower for kw in ["performance", "slow", "optimize", "bottleneck"]):
        category = "performance"
    elif any(kw in name_lower for kw in ["security", "vulnerability", "injection", "xss"]):
        category = "security"
    elif any(kw in name_lower for kw in ["architecture", "design", "pattern", "structure"]):
        category = "architecture"

    # ── Technical tags inference ──────────────────────────────
    technical_tags = []
    kw_map = {
        "redis": ["redis", "cache", "ttl", "expiration"],
        "database": ["database", "sql", "persistence", "fallback"],
        "state": ["state", "state-management", "session", "lifecycle"],
        "idempotency": ["idempotency", "deduplication", "exactly-once"],
        "java": ["java", "backend", "service"],
        "interview": ["interview", "session", "application"],
        "service": ["service", "api", "endpoint"],
        "answer": ["answer", "request", "response"],
        "rag": ["rag", "retrieval", "vector", "embedding"],
        "llm": ["llm", "ai", "model", "generation"],
        "test": ["testing", "validation", "assertion"],
        "concurrency": ["concurrency", "locking", "race-condition"],
        "atomic": ["atomic", "transaction", "rollback"],
        "write": ["dual-write", "consistency", "write-path"],
        "read": ["read-path", "query", "fetch"],
        "null": ["null", "nil", "null-check", "defensive"],
        "exception": ["exception", "error-handling", "resilience"],
        "lock": ["locking", "distributed-lock", "mutex"],
        "stream": ["streaming", "sse", "async"],
        "mq": ["message-queue", "rabbitmq", "event"],
        "question": ["question", "quiz", "assessment"],
        "count": ["counting", "increment", "drift"],
    }

    for key, tags in kw_map.items():
        if key in name_lower:
            technical_tags.extend(tags)

    # Deduplicate and limit
    seen = set()
    unique_tags = []
    for t in technical_tags:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)
    technical_tags = unique_tags[:10]

    return {
        "domain": domain,
        "category": category,
        "technical_tags": technical_tags,
    }


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

    # Infer domain-aware metadata for retrieval compatibility
    domain_meta = _infer_domain_metadata(pattern_name)

    # Create .md file
    os.makedirs(HYPOTHESIS_DIR, exist_ok=True)
    md_filename = f"{memory_id}.md"
    md_path = os.path.join(HYPOTHESIS_DIR, md_filename)

    tags_yaml = "\n".join([f"  - {t}" for t in ["auto-bootstrapped", clean.lower()] + domain_meta["technical_tags"]])

    md_content = f"""```yaml
memory_id: {memory_id}
type: hypothesis
category: {domain_meta["category"]}
domain: {domain_meta["domain"]}
source_loop: {source_loop_id}
source_team: {source_team_id}
source_agent: {agent_role}
evidence_level: hypothesis
confidence: low
observation_count: 1
created_at: {datetime.now(timezone.utc).isoformat()}
tags:
{tags_yaml}
```

# {pattern_name}

## Pattern

{lesson[:500] if lesson else 'Auto-bootstrapped from multi-agent execution.'}

## Context

{context[:200] if context else 'First observed in multi-agent team execution.'}

## Domain

- Domain: {domain_meta["domain"]}
- Technical Tags: {', '.join(domain_meta["technical_tags"])}

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
    all_tags = ["auto-bootstrapped", clean.lower()] + domain_meta["technical_tags"]
    new_entry = {
        "memory_id": memory_id,
        "file": f"memory/hypotheses/{md_filename}",
        "type": "hypothesis",
        "category": domain_meta["category"],
        "domain": domain_meta["domain"],
        "source_loop": source_loop_id,
        "source_team": source_team_id,
        "source_agent": agent_role,
        "source_task": source_loop_id,
        "evidence_level": "hypothesis",
        "confidence": "low",
        "observation_count": 1,
        "tags": all_tags,
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


# ── Phase 8.2.1.3: Observation Log Functions ──────────────────────

def load_observation_log() -> dict:
    """Load the memory observation log."""
    if not os.path.exists(OBSERVATION_LOG_FILE):
        return {"version": "1.0", "phase": "8.2.1.3", "observations": []}
    with open(OBSERVATION_LOG_FILE) as f:
        return yaml.safe_load(f) or {"version": "1.0", "phase": "8.2.1.3", "observations": []}


def save_observation_log(log: dict):
    """Save the observation log to disk."""
    os.makedirs(os.path.dirname(OBSERVATION_LOG_FILE), exist_ok=True)
    with open(OBSERVATION_LOG_FILE, "w") as f:
        yaml.dump(log, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def append_observation(memory_id: str, source_loop: str, source_team: str,
                       session_id: str, output_hash: str, quality_score: float,
                       agent_role: str = "backend", origin: str = "reinforce") -> bool:
    """
    Append an observation to the observation log.
    Deduplicates by (memory_id, source_loop).
    Returns True if appended, False if duplicate.
    """
    log = load_observation_log()
    observations = log.get("observations", [])

    # Dedup check
    for obs in observations:
        if obs.get("memory_id") == memory_id and obs.get("source_loop") == source_loop:
            return False

    observation = {
        "memory_id": memory_id,
        "source_loop": source_loop,
        "source_team": source_team,
        "session_id": session_id,
        "output_hash": output_hash,
        "quality_score": quality_score,
        "agent_role": agent_role,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "origin": origin,
    }

    observations.append(observation)
    log["observations"] = observations
    save_observation_log(log)
    return True