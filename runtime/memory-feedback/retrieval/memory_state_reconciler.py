#!/usr/bin/env python3
"""
Memory State Reconciler — Phase 5.8.1
Ensures retrieval-index.yaml is consistent with canonical .md files.

Usage:
  python3 memory_state_reconciler.py --check     # Audit only
  python3 memory_state_reconciler.py --repair    # Fix derived state

Design:
  memory/*.md = canonical source of truth
  retrieval-index.yaml = derived index (synced from canonical)
  decay-state.yaml = derived runtime state (computed from index)

Never modifies:
  - .md file content (canonical)
  - traces (execution truth)
  - promotion/validation/evaluation results (historical)
"""

import yaml
import os
import re
import sys
from datetime import datetime, timezone
from copy import deepcopy

BASE = "/home/shade/.agents"
INDEX_FILE = os.path.join(BASE, "memory", "retrieval-index.yaml")
MEMORY_DIR = os.path.join(BASE, "memory")
LOG_DIR = os.path.join(BASE, "runtime", "logs")
CHANGE_LOG = os.path.join(LOG_DIR, "memory-state-change-history.md")

# Fields that are synced from canonical .md → index
CANONICAL_FIELDS = [
    "evidence_level",
    "confidence",
    "observation_count",
    "status",
    "last_validated_at",
]

# Fields that are index-only (not in .md frontmatter)
INDEX_ONLY_FIELDS = [
    "quality_delta",
    "winner",
    "cost_delta",
    "file",
    "type",
    "category",
    "source_task",
    "source_tasks",
    "tags",
    "roles",
    "difficulty",
]


def read_memory_frontmatter(filepath):
    """Extract YAML frontmatter from a memory .md file."""
    if not os.path.exists(filepath):
        return {}
    with open(filepath) as f:
        content = f.read()
    match = re.search(r"```yaml\n(.*?)\n```", content, re.DOTALL)
    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return {}
    return {}


def load_index():
    with open(INDEX_FILE) as f:
        return yaml.safe_load(f)


def save_index(data):
    with open(INDEX_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def check_consistency():
    """Check all memories for drift between canonical and index."""
    index = load_index()
    memories = index.get("memories", [])
    results = {"consistent": True, "total": len(memories), "drifted": [], "ok": 0}

    for mem in memories:
        mid = mem["memory_id"]
        filepath = os.path.join(BASE, mem.get("file", ""))
        canonical = read_memory_frontmatter(filepath)

        if not canonical:
            continue

        drifts = []
        for field in CANONICAL_FIELDS:
            canonical_val = canonical.get(field)
            index_val = mem.get(field)

            # Normalize: None vs missing is equivalent
            if canonical_val is None and index_val is None:
                continue

            if canonical_val != index_val:
                drifts.append({
                    "memory_id": mid,
                    "field": field,
                    "canonical": canonical_val,
                    "index": index_val,
                    "source": "memory .md file",
                })

        if drifts:
            results["drifted"].append({"memory_id": mid, "drifts": drifts})
            results["consistent"] = False
        else:
            results["ok"] += 1

    return results


def repair_index():
    """Repair retrieval-index.yaml to match canonical .md files."""
    index = load_index()
    memories = index.get("memories", [])
    changes = []
    old_snapshot = deepcopy(memories)

    for mem in memories:
        mid = mem["memory_id"]
        filepath = os.path.join(BASE, mem.get("file", ""))
        canonical = read_memory_frontmatter(filepath)

        if not canonical:
            continue

        mem_changed = False
        for field in CANONICAL_FIELDS:
            canonical_val = canonical.get(field)
            index_val = mem.get(field)

            if canonical_val is None and index_val is None:
                continue

            if canonical_val != index_val:
                old_val = index_val
                mem[field] = canonical_val
                changes.append({
                    "memory_id": mid,
                    "field": field,
                    "old_value": old_val,
                    "new_value": canonical_val,
                    "source": "memory .md file",
                })
                mem_changed = True

        # Phase 5.8.1: Per-memory state versioning
        if mem_changed:
            current_version = mem.get("state_version", 0)
            mem["state_version"] = current_version + 1

    if changes:
        # Global index version
        index.setdefault("index_version", 0)
        index["index_version"] += 1
        index["last_reconciled_at"] = datetime.now(timezone.utc).isoformat()
        index["last_reconciled_changes"] = len(changes)

        save_index(index)
        log_changes(changes, old_snapshot)

    return changes


def log_changes(changes, old_snapshot):
    """Append to state change history log."""
    os.makedirs(LOG_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []

    if not os.path.exists(CHANGE_LOG):
        lines.append("# Memory State Change History\n")
        lines.append("| Timestamp | Memory ID | Field | Old Value | New Value | Source |\n")
        lines.append("|-----------|-----------|-------|-----------|-----------|--------|\n")

    for ch in changes:
        lines.append(
            f"| {timestamp} | {ch['memory_id']} | {ch['field']} "
            f"| {ch['old_value']} | {ch['new_value']} | {ch['source']} |\n"
        )

    with open(CHANGE_LOG, "a") as f:
        f.writelines(lines)


def print_check(results):
    """Print --check results in required format."""
    if results["consistent"]:
        print("CONSISTENT")
        print(f"  {results['total']} memories checked, {results['ok']} OK, 0 drifted")
        return 0

    print("INCONSISTENT")
    print(f"  {results['total']} memories checked, {results['ok']} OK, {len(results['drifted'])} drifted\n")

    for entry in results["drifted"]:
        mid = entry["memory_id"]
        for d in entry["drifts"]:
            print(f"  {mid}")
            print(f"    field:     {d['field']}")
            print(f"    expected:  {d['canonical']}")
            print(f"    actual:    {d['index']}")
            print(f"    source:    {d['source']}")
            print()

    return 1


def print_repair(changes):
    """Print --repair results."""
    if not changes:
        print("No changes needed. Index is already consistent.")
        return 0

    print(f"Repaired {len(changes)} field(s) in retrieval-index.yaml:\n")
    for ch in changes:
        print(f"  {ch['memory_id']}.{ch['field']}: {ch['old_value']} → {ch['new_value']}")
    print(f"\nChange log: {CHANGE_LOG}")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("--check", "--repair"):
        print("Usage: python3 memory_state_reconciler.py --check | --repair")
        sys.exit(2)

    mode = sys.argv[1]

    if mode == "--check":
        results = check_consistency()
        sys.exit(print_check(results))

    elif mode == "--repair":
        changes = repair_index()
        sys.exit(print_repair(changes))


if __name__ == "__main__":
    main()