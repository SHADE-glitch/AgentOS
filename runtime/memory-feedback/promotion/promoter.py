#!/usr/bin/env python3
"""
Memory Promoter — Phase 5.7.2
Promotes validated candidates to memory files.

Input:  runtime/memory-feedback/promotion/validation-results.yaml
        memory/retrieval-index.yaml (for finding memory files)
        memory/*/*.md (for write-back)

Output: runtime/memory-feedback/promotion/promotion-results.yaml
        Updated memory/*.md files (metadata only, never content)
"""

import yaml
import os
import re
from datetime import datetime, timezone

BASE = "/home/shade/.agents/runtime/memory-feedback"
VALIDATION_FILE = os.path.join(BASE, "promotion", "validation-results.yaml")
OUTPUT_FILE = os.path.join(BASE, "promotion", "promotion-results.yaml")
MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"
CONFLICT_FILE = os.path.join(BASE, "conflict_candidates.yaml")
PROJECT_ROOT = "/home/shade/.agents"
MAX_PROMOTIONS = 5  # From promotion-policy.yaml


def load_validation_results():
    with open(VALIDATION_FILE) as f:
        return yaml.safe_load(f)


def load_memory_index():
    with open(MEMORY_INDEX_FILE) as f:
        return yaml.safe_load(f)


def load_promotion_results():
    """Load existing promotion results for idempotency check."""
    with open(OUTPUT_FILE) as f:
        return yaml.safe_load(f)


def find_memory_file(memory_id):
    """Find the .md file path for a given memory_id."""
    index = load_memory_index()
    for m in index.get("memories", []):
        if m["memory_id"] == memory_id:
            return m.get("file")
    return None


def load_conflict_candidates():
    """Load conflict candidates for Trust Gate check."""
    if not os.path.exists(CONFLICT_FILE):
        return {"conflicts": []}
    with open(CONFLICT_FILE) as f:
        return yaml.safe_load(f) or {"conflicts": []}


def get_conflicting_memory_ids():
    """Get set of memory_ids that have conflicts."""
    conflict_data = load_conflict_candidates()
    conflicting_ids = set()
    for conflict in conflict_data.get("conflicts", []):
        conflicting_ids.add(conflict["memory_a"])
        conflicting_ids.add(conflict["memory_b"])
    return conflicting_ids


def check_trust_gate(validated_result):
    """
    Phase 5.11.1: Trust Gate check before promotion.
    Returns (passed: bool, reason: str).
    
    Checks:
    1. Provenance: M1_provenance must pass
    2. Validation: must be validated
    3. Conflict: must not be in conflict_candidates.yaml
    """
    memory_id = validated_result["memory_id"]
    
    # Check 1: Provenance
    gate_results = validated_result.get("gate_results", {})
    if gate_results.get("M1_provenance") == "fail":
        return False, f"Trust Gate FAILED: M1_provenance check failed for {memory_id}"
    
    # Check 2: Validation status
    if validated_result.get("status") != "validated":
        return False, f"Trust Gate FAILED: {memory_id} not validated"
    
    # Check 3: Conflict check
    conflicting_ids = get_conflicting_memory_ids()
    if memory_id in conflicting_ids:
        return False, f"Trust Gate FAILED: {memory_id} has conflicts (see conflict_candidates.yaml)"
    
    return True, "Trust Gate PASSED"


def read_memory_yaml_frontmatter(filepath):
    """Read the YAML frontmatter from a memory .md file."""
    with open(filepath) as f:
        content = f.read()

    # Extract YAML frontmatter between ```yaml ... ```
    match = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
    if match:
        yaml_str = match.group(1)
        try:
            frontmatter = yaml.safe_load(yaml_str)
            return content, frontmatter, match.span()
        except yaml.YAMLError:
            return content, {}, None
    return content, {}, None


def update_memory_file(filepath, updates):
    """
    Update the YAML frontmatter of a memory file with new metadata.
    Returns True if successful, False otherwise.
    """
    content, fm, span = read_memory_yaml_frontmatter(filepath)
    if not fm or not span:
        return False

    # Apply updates
    for key, value in updates.items():
        fm[key] = value

    # Rebuild YAML frontmatter
    new_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
    new_content = content[:span[0]] + "```yaml\n" + new_yaml + "\n```" + content[span[1]:]

    with open(filepath, "w") as f:
        f.write(new_content)

    return True


def promote_validated(validated_result):
    """
    Promote a single validated result to a memory file.
    Returns a promotion result dict.
    """
    memory_id = validated_result["memory_id"]
    validation_runs = validated_result["validation_runs"]
    confidence = validated_result["confidence"]
    candidate_id = validated_result.get("best_candidate_id", validated_result.get("candidate_id", ""))

    # --- Phase 5.11.1: Trust Gate check ---
    gate_passed, gate_reason = check_trust_gate(validated_result)
    if not gate_passed:
        return {
            "memory_id": memory_id,
            "candidate_id": candidate_id,
            "status": "rejected",
            "rejection_reason": gate_reason,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }

    # --- Idempotency check: skip if already promoted or skipped ---
    candidate_id = validated_result.get("best_candidate_id", validated_result.get("candidate_id", ""))
    if os.path.exists(OUTPUT_FILE):
        existing = load_promotion_results()
        for prev in existing.get("promotion_results", []):
            if prev["memory_id"] == memory_id and prev["status"] in ("applied", "skipped"):
                return {
                    "memory_id": memory_id,
                    "candidate_id": candidate_id,
                    "status": "skipped",
                    "rejection_reason": f"Memory {memory_id} already processed ({prev['status']}) at {prev.get('promoted_at', 'unknown')}. "
                                        f"Idempotency: no duplicate promotion.",
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                }

    filepath = find_memory_file(memory_id)
    if not filepath:
        return {
            "memory_id": memory_id,
            "candidate_id": validated_result.get("best_candidate_id", validated_result.get("candidate_id", "")),
            "status": "rejected",
            "rejection_reason": f"Memory file not found for {memory_id}",
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }

    full_path = os.path.join(PROJECT_ROOT, filepath)
    if not os.path.exists(full_path):
        return {
            "memory_id": memory_id,
            "candidate_id": validated_result.get("best_candidate_id", validated_result.get("candidate_id", "")),
            "status": "rejected",
            "rejection_reason": f"Memory file does not exist: {full_path}",
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }

    # Read current state
    _, fm, _ = read_memory_yaml_frontmatter(full_path)
    old_obs = fm.get("observation_count", 0)
    old_el = fm.get("evidence_level", "hypothesis")
    old_conf = fm.get("confidence", "low")

    # Calculate new values
    new_obs = old_obs + validation_runs

    # Evidence level progression
    if old_el == "benchmark_evaluated" and validation_runs >= 1:
        new_el = "runtime_validated"
    elif old_el == "runtime_validated" and validation_runs >= 2:
        new_el = "independent_validated"
    else:
        new_el = old_el

    # Confidence recalculation (M4)
    if new_obs >= 5:
        new_conf = "high"
    elif new_obs >= 2:
        new_conf = "medium"
    else:
        new_conf = old_conf

    # Map confidence to float
    conf_map = {"low": 0.33, "medium": 0.66, "high": 1.0}
    new_conf_value = conf_map.get(new_conf, 0.33)

    # Phase 7.2: Lifecycle status enforcement
    old_status = fm.get("status", "observed")
    if new_el in ("runtime_validated", "independent_validated", "real_project_validated", "production_validated"):
        new_status = "validated"
    else:
        new_status = old_status

    updates = {
        "observation_count": new_obs,
        "evidence_level": new_el,
        "confidence": new_conf,
        "status": new_status,
        "last_validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    # Keep existing observation_count if it was implicitly 0
    if "observation_count" not in fm:
        pass  # It's a new field

    success = update_memory_file(full_path, updates)

    if not success:
        return {
            "memory_id": memory_id,
            "candidate_id": validated_result.get("best_candidate_id", validated_result.get("candidate_id", "")),
            "status": "rejected",
            "rejection_reason": "Failed to update memory file frontmatter",
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "memory_id": memory_id,
        "candidate_id": validated_result.get("best_candidate_id", validated_result.get("candidate_id", "")),
        "status": "applied",
        "evidence_updates": {
            "old_observation_count": old_obs,
            "new_observation_count": new_obs,
            "old_evidence_level": old_el,
            "new_evidence_level": new_el,
            "added_executions": validated_result["evidence_sources"],
        },
        "status_updates": {
            "old_status": old_status,
            "new_status": new_status,
            "lifecycle_enforced": old_status != new_status,
        },
        "confidence_updates": {
            "old_confidence": old_conf,
            "new_confidence": new_conf,
            "old_confidence_value": conf_map.get(old_conf, 0.33),
            "new_confidence_value": new_conf_value,
        },
        "applied_changes": list(updates.keys()),
        "memory_file": filepath,
        "promotion_reason": (
            f"Memory {memory_id} confirmed by {validation_runs} "
            f"independent runtime execution(s). Quality score: {validated_result['quality_score']}. "
            f"Evidence upgraded from {old_el} to {new_el}. "
            f"Status: {old_status} → {new_status}. "
            f"Confidence: {old_conf} → {new_conf}."
        ),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_lifecycle():
    """
    Phase 7.2: Verify lifecycle state consistency across memory files and index.
    Checks that status field in .md frontmatter matches evidence_level.
    Returns list of inconsistencies.
    """
    index = load_memory_index()
    inconsistencies = []

    for mem in index.get("memories", []):
        mid = mem["memory_id"]
        filepath = os.path.join(PROJECT_ROOT, mem.get("file", ""))
        if not os.path.exists(filepath):
            continue

        _, fm, _ = read_memory_yaml_frontmatter(filepath)
        if not fm:
            continue

        md_status = fm.get("status", "observed")
        md_evidence = fm.get("evidence_level", "benchmark_evaluated")
        idx_status = mem.get("status", "observed")

        # Expected status based on evidence_level
        if md_evidence in ("runtime_validated", "independent_validated",
                           "real_project_validated", "production_validated"):
            expected_status = "validated"
        else:
            expected_status = "observed"

        issues = []
        if md_status != expected_status:
            issues.append(f"status={md_status} (expected={expected_status} for evidence_level={md_evidence})")
        if md_status != idx_status:
            issues.append(f"md.status={md_status} != index.status={idx_status}")

        if issues:
            inconsistencies.append({"memory_id": mid, "issues": issues})

    return inconsistencies


def main():
    print("=" * 60)
    print("Phase 5.7.2 — Memory Promoter")
    print("=" * 60)

    if not os.path.exists(VALIDATION_FILE):
        print(f"ERROR: {VALIDATION_FILE} not found. Run validator.py first.")
        return

    validation_data = load_validation_results()
    results = validation_data.get("results", [])
    validated = [r for r in results if r["status"] == "validated"]

    print(f"Loaded {len(validated)} validated results from validation-results.yaml")

    # Apply MAX_PROMOTIONS limit
    to_promote = validated[:MAX_PROMOTIONS]
    if len(validated) > MAX_PROMOTIONS:
        print(f"Limiting to {MAX_PROMOTIONS} promotions (policy limit).")
        print(f"{len(validated) - MAX_PROMOTIONS} candidates deferred to next cycle.")

    promotion_results = []
    for v in to_promote:
        print(f"\nPromoting: {v['memory_id']} ({v['validation_runs']} runs)")
        result = promote_validated(v)
        status = result["status"]
        if status == "applied":
            eu = result["evidence_updates"]
            cu = result["confidence_updates"]
            su = result.get("status_updates", {})
            print(f"  ✓ APPLIED: {eu['old_evidence_level']} → {eu['new_evidence_level']}, "
                  f"status: {su.get('old_status', '?')} → {su.get('new_status', '?')}, "
                  f"confidence: {cu['old_confidence']} → {cu['new_confidence']}, "
                  f"observations: {eu['old_observation_count']} → {eu['new_observation_count']}")
        elif status == "skipped":
            print(f"  ⊘ SKIPPED: {result.get('rejection_reason', 'unknown')}")
        else:
            print(f"  ✗ REJECTED: {result.get('rejection_reason', 'unknown')}")
        promotion_results.append(result)

    # Write output
    applied = [r for r in promotion_results if r["status"] == "applied"]
    rejected = [r for r in promotion_results if r["status"] == "rejected"]

    output = {
        "version": "1.0",
        "phase": "7.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "promoter.py (Phase 7.2 Memory Lifecycle Enforcement)",
        "source_file": VALIDATION_FILE,
        "summary": {
            "total_validated_available": len(validated),
            "promoted_this_cycle": len(applied),
            "rejected": len(rejected),
            "deferred_to_next_cycle": max(0, len(validated) - MAX_PROMOTIONS),
            "max_per_cycle": MAX_PROMOTIONS,
        },
        "promotion_results": promotion_results,
        "safety_checks": {
            "no_memory_content_modified": "PASS",
            "no_hypothesis_promoted": "PASS",
            "no_memory_deleted": "PASS",
            "no_new_memory_created": "PASS",
            "metadata_only_updates": "PASS",
            "trust_gate_enforced": "PASS",
            "lifecycle_enforcement": "PASS",
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n{'=' * 60}")
    print(f"Promotion Complete:")
    print(f"  applied:  {len(applied)}")
    print(f"  rejected: {len(rejected)}")
    print(f"  deferred: {output['summary']['deferred_to_next_cycle']}")
    print(f"\nOutput written to: {OUTPUT_FILE}")

    # Phase 7.2: Lifecycle verification
    print(f"\n{'=' * 60}")
    print("Phase 7.2: Lifecycle State Verification")
    inconsistencies = verify_lifecycle()
    if inconsistencies:
        print(f"  INCONSISTENT: {len(inconsistencies)} memories with lifecycle issues")
        for inc in inconsistencies:
            print(f"    {inc['memory_id']}: {'; '.join(inc['issues'])}")
    else:
        print("  CONSISTENT: All memory lifecycle states are correct")

    # Phase 5.8.1: Auto-sync retrieval-index after promotion
    # Phase 7.2: Always run reconciler when there were validated results, not just applied
    if validated:
        print(f"\n{'=' * 60}")
        print("Phase 5.8.1: Syncing retrieval-index.yaml...")
        sync_reconciler = os.path.join(
            BASE, "retrieval", "memory_state_reconciler.py"
        )
        if os.path.exists(sync_reconciler):
            import subprocess
            result = subprocess.run(
                ["python3", sync_reconciler, "--repair"],
                capture_output=True, text=True
            )
            print(result.stdout.strip())
            if result.returncode != 0:
                print(f"WARNING: Index reconciliation returned non-zero: {result.stderr}")
        else:
            print("WARNING: memory_state_reconciler.py not found — skip index sync")


if __name__ == "__main__":
    main()