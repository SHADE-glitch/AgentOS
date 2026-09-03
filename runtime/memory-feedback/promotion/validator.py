#!/usr/bin/env python3
"""
Memory Validator — Phase 5.7.2
Validates candidates from memory-candidates.yaml against promotion criteria.

Groups candidates by memory_id, counts independent executions,
uses best quality score, and applies validation rules.

Input:  runtime/memory-feedback/memory-candidates.yaml
Output: runtime/memory-feedback/promotion/validation-results.yaml
"""

import yaml
import os
from datetime import datetime, timezone
from collections import defaultdict

BASE = "/home/shade/.agents/runtime/memory-feedback"
CANDIDATES_FILE = os.path.join(BASE, "memory-candidates.yaml")
OUTPUT_FILE = os.path.join(BASE, "promotion", "validation-results.yaml")
MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"

# Thresholds from promotion-policy.yaml
QUALITY_THRESHOLD = 3.0
MIN_OBSERVATIONS = 2  # M4: medium confidence requires >= 2
HYPOTHESIS_MIN_OBSERVATIONS = 1  # Phase 8.2.1.1: H-xxx hypotheses only need 1 observation
MAX_OBSERVATIONS_FOR_FULL_CONFIDENCE = 5
OBSERVATION_LOG_FILE = os.path.join(BASE, "memory-observation-log.yaml")
OBSERVATION_LOG_MIN_OBSERVATIONS = 2  # Phase 8.2.1.3: min observations to synthesize a group


def load_candidates():
    with open(CANDIDATES_FILE) as f:
        return yaml.safe_load(f)


def load_memory_index():
    if not os.path.exists(MEMORY_INDEX_FILE):
        return {}
    with open(MEMORY_INDEX_FILE) as f:
        return yaml.safe_load(f)


def find_memory_metadata(memory_id):
    """Find the existing metadata for a memory_id from retrieval-index."""
    index = load_memory_index()
    for m in index.get("memories", []):
        if m["memory_id"] == memory_id:
            return m
    return None


def group_candidates_by_memory(candidates):
    """Group all candidates by target_memory, collecting all evidence."""
    groups = defaultdict(lambda: {
        "memory_id": "",
        "candidates": [],
        "executions": set(),
        "best_quality": 0,
        "best_candidate_id": "",
        "all_quality_scores": [],
        "all_session_ids": set(),
        "all_output_hashes": set(),
    })

    for c in candidates:
        mid = c["target_memory"]
        groups[mid]["memory_id"] = mid
        groups[mid]["candidates"].append(c)
        groups[mid]["executions"].add(c["source_execution"])

        qs = c.get("quality_score", 0)
        groups[mid]["all_quality_scores"].append(qs)
        if qs > groups[mid]["best_quality"]:
            groups[mid]["best_quality"] = qs
            groups[mid]["best_candidate_id"] = c["candidate_id"]

        ev = c.get("evidence", {})
        if ev.get("session_id"):
            groups[mid]["all_session_ids"].add(ev["session_id"])
        if ev.get("output_hash"):
            groups[mid]["all_output_hashes"].add(ev["output_hash"])

    return groups


def validate_memory_group(memory_id, group):
    """
    Validate a memory across all its candidates.
    Returns (status, result_dict).

    Phase 8.2.1.1 — Hypothesis Lifecycle:
      H-xxx memories (hypotheses) are allowed with >=1 observation.
      They enter as "hypothesis" status, not "validated".
      On second observation, they graduate to "validated".

    Lifecycle:
      Candidate → Hypothesis (1 obs) → Validated (2 obs) → Promoted
    """
    validation_runs = len(group["executions"])
    best_qs = group["best_quality"]
    ctype = group["candidates"][0].get("candidate_type", "") if group["candidates"] else ""
    is_hypothesis = memory_id.upper().startswith("H-")

    # Phase 8.2.1.1: H-xxx hypotheses only need 1 observation
    required_obs = HYPOTHESIS_MIN_OBSERVATIONS if is_hypothesis else MIN_OBSERVATIONS

    checks = {
        "is_real_execution": len(group["all_session_ids"]) > 0,
        "has_execution_evidence": len(group["all_output_hashes"]) > 0,
        "has_independent_verification": validation_runs >= required_obs,
        "quality_above_threshold": best_qs >= QUALITY_THRESHOLD,
        "not_hypothesis": ctype != "create_hypothesis" and not is_hypothesis,
    }

    rejection_reason = None

    # REJECT conditions
    if not checks["is_real_execution"]:
        status = "rejected"
        rejection_reason = "Missing session_id — cannot verify as real execution"
    elif not checks["has_execution_evidence"]:
        status = "rejected"
        rejection_reason = "Missing output_hash — insufficient execution evidence"
    elif not checks["quality_above_threshold"]:
        status = "rejected"
        rejection_reason = f"Best quality score {best_qs} below threshold {QUALITY_THRESHOLD} (scores: {group['all_quality_scores']})"
    elif ctype == "create_hypothesis" and not is_hypothesis:
        status = "rejected"
        rejection_reason = "Hypothesis candidates are held, never auto-promoted (Rule 5)"
    elif ctype == "weaken":
        status = "rejected"
        rejection_reason = "Weaken candidates require human review, not auto-processed"
    elif not checks["has_independent_verification"]:
        status = "rejected"
        rejection_reason = f"Only {validation_runs} observation(s). Need >= {required_obs} independent executions (M4)."

    # Phase 8.2.1.1: H-xxx with enough observations → hypothesis status
    elif is_hypothesis:
        if validation_runs >= MIN_OBSERVATIONS:
            status = "validated"  # Graduate: second observation confirms hypothesis
        else:
            status = "hypothesis"  # First observation: enter as hypothesis

    # VALIDATED
    else:
        status = "validated"

    # Calculate confidence
    confidence = min(validation_runs / MAX_OBSERVATIONS_FOR_FULL_CONFIDENCE, 1.0)

    # Gate results
    meta = find_memory_metadata(memory_id)
    gate_results = {}
    if meta:
        # Phase 5.11.1: Handle both source_task and source_tasks formats
        has_provenance = bool(
            meta.get("source_task") or 
            meta.get("source_tasks") or 
            (meta.get("source", {}).get("task_id") if isinstance(meta.get("source"), dict) else False)
        )
        gate_results["M1_provenance"] = "pass" if has_provenance else "fail"
        el = meta.get("evidence_level", "hypothesis")
        gate_results["M2_evidence_level"] = "pass" if el in [
            "benchmark_evaluated", "runtime_validated", "independent_validated",
            "real_project_validated", "production_validated"
        ] else "fail"
        gate_results["M3_duplicate"] = "skip"
        gate_results["M4_confidence"] = "pass" if validation_runs >= 2 else "fail"
        gate_results["M5_relevance"] = "pass" if meta.get("category") else "fail"
        gate_results["M6_staleness"] = "pass"
    else:
        # Phase 8.2.1.1: H-xxx hypotheses auto-bootstrapped by resolver
        if is_hypothesis:
            gate_results = {
                "M1_provenance": "skip", "M2_evidence_level": "skip",
                "M3_duplicate": "skip",
                "M4_confidence": "pass" if validation_runs >= 1 else "fail",
                "M5_relevance": "skip", "M6_staleness": "skip",
            }
        else:
            gate_results = {f"M{i}_provenance" if i == 1 else f"M{i}": "skip" for i in range(1, 7)}
            status = "rejected"
            rejection_reason = f"Memory {memory_id} not found in retrieval-index.yaml"

    return status, {
        "memory_id": memory_id,
        "best_candidate_id": group["best_candidate_id"],
        "status": status,
        "validation_runs": validation_runs,
        "quality_score": best_qs,
        "all_quality_scores": group["all_quality_scores"],
        "confidence": round(confidence, 2),
        "gate_results": gate_results,
        "evidence_sources": sorted(group["executions"]),
        "unique_sessions": len(group["all_session_ids"]),
        "checks": checks,
        "rejection_reason": rejection_reason,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        **({"cross_loop": {
            "prior_observations": group["cross_loop_observations"],
            "sources": group.get("cross_loop_sources", []),
        }} if group.get("cross_loop_observations") else {}),
    }


def load_observation_log():
    """Load the memory observation log."""
    if not os.path.exists(OBSERVATION_LOG_FILE):
        return []
    with open(OBSERVATION_LOG_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("observations", [])


def enrich_groups_with_observation_log(groups):
    """
    Phase 8.2.1.3: Enrich existing candidate groups with cross-loop observations
    from the observation log. Only applies to H-xxx memories.

    For each H-xxx group, reads the observation log and adds historical
    observations to the group's executions, session_ids, output_hashes,
    and quality_scores. Updates best_quality to max of all.

    Returns: enriched groups dict (same structure, with added fields)
    """
    observations = load_observation_log()
    if not observations:
        return groups

    for memory_id, group in list(groups.items()):
        if not memory_id.upper().startswith("H-"):
            continue

        # Collect observations for this memory from the log
        log_obs = [o for o in observations if o.get("memory_id") == memory_id]
        if not log_obs:
            continue

        cross_loop_sources = []
        for obs in log_obs:
            source_loop = obs.get("source_loop")
            if source_loop and source_loop not in group["executions"]:
                group["executions"].add(source_loop)
                cross_loop_sources.append(source_loop)

            qs = obs.get("quality_score", 0)
            if qs > group["best_quality"]:
                group["best_quality"] = qs
            group["all_quality_scores"].append(qs)

            sid = obs.get("session_id")
            if sid:
                group["all_session_ids"].add(sid)
            oh = obs.get("output_hash")
            if oh:
                group["all_output_hashes"].add(oh)

        group["cross_loop_observations"] = len(log_obs)
        group["cross_loop_sources"] = cross_loop_sources

    return groups


def synthesize_groups_from_observation_log(groups):
    """
    Phase 8.2.1.3: Create candidate groups for H-xxx memories that have
    observations in the observation log but no candidate group in the
    current groups dict.

    This handles the case where a hypothesis has 2+ observations across
    multiple loops but no candidate was generated in the current loop.

    Returns: groups dict with synthesized entries added
    """
    observations = load_observation_log()
    if not observations:
        return groups

    # Group observations by memory_id
    obs_by_memory = defaultdict(list)
    for obs in observations:
        mid = obs.get("memory_id", "")
        if mid.upper().startswith("H-"):
            obs_by_memory[mid].append(obs)

    for memory_id, mem_obs in obs_by_memory.items():
        # Skip if already has a candidate group
        if memory_id in groups:
            continue

        # Skip if insufficient observations
        if len(mem_obs) < OBSERVATION_LOG_MIN_OBSERVATIONS:
            continue

        # Synthesize a group from observation log entries
        executions = set()
        best_quality = 0
        all_quality_scores = []
        all_session_ids = set()
        all_output_hashes = set()

        for obs in mem_obs:
            sl = obs.get("source_loop")
            if sl:
                executions.add(sl)

            qs = obs.get("quality_score", 0)
            all_quality_scores.append(qs)
            if qs > best_quality:
                best_quality = qs

            sid = obs.get("session_id")
            if sid:
                all_session_ids.add(sid)
            oh = obs.get("output_hash")
            if oh:
                all_output_hashes.add(oh)

        groups[memory_id] = {
            "memory_id": memory_id,
            "candidates": [],
            "executions": executions,
            "best_quality": best_quality,
            "best_candidate_id": "",
            "all_quality_scores": all_quality_scores,
            "all_session_ids": all_session_ids,
            "all_output_hashes": all_output_hashes,
            "cross_loop_observations": len(mem_obs),
            "cross_loop_sources": sorted(executions),
            "synthesized": True,
        }

    return groups


def validate_candidates(candidates, quiet=False):
    """
    Validate a list of candidates directly (programmatic entry point).
    Phase 5.8.2.2: Added for loop controller integration.

    Args:
        candidates: list of candidate dicts from collector
        quiet: suppress console output

    Returns:
        list of validation result dicts
    """
    if not candidates:
        if not quiet:
            print("No candidates from memory-candidates.yaml.")

    groups = group_candidates_by_memory(candidates)
    if not quiet and candidates:
        print(f"Grouped {len(candidates)} candidates → {len(groups)} memory groups")

    # Phase 8.2.1.3: Cross-loop enrichment from observation log
    groups = enrich_groups_with_observation_log(groups)

    # Phase 8.2.1.3: Synthesize groups for H-xxx from observation log only
    groups = synthesize_groups_from_observation_log(groups)

    if not groups:
        if not quiet:
            print("No memory groups to validate.")
        return []

    if not quiet:
        print(f"Validating {len(groups)} memory groups (after enrichment)")

    results = []
    for memory_id, group in sorted(groups.items()):
        status, result = validate_memory_group(memory_id, group)
        if not quiet:
            print(f"  {memory_id}: {status} (runs={result['validation_runs']}, quality={result['quality_score']})")
            if result.get("rejection_reason"):
                print(f"    rejected: {result['rejection_reason']}")
        results.append(result)

    return results


def main():
    print("=" * 60)
    print("Phase 5.8.2.2 — Memory Validator")
    print("=" * 60)

    if not os.path.exists(CANDIDATES_FILE):
        print(f"ERROR: {CANDIDATES_FILE} not found.")
        return

    candidates_data = load_candidates()
    candidates = candidates_data.get("candidates", [])
    print(f"Loaded {len(candidates)} candidates from memory-candidates.yaml")

    results = validate_candidates(candidates)

    validated = [r for r in results if r["status"] == "validated"]
    rejected = [r for r in results if r["status"] == "rejected"]

    print(f"\n{'=' * 60}")
    print(f"Validation Complete:")
    print(f"  memories evaluated: {len(results)}")
    print(f"  validated: {len(validated)}")
    print(f"  rejected:  {len(rejected)}")

    if rejected:
        print(f"\nRejected memories:")
        for r in rejected:
            print(f"  - {r['memory_id']}: {r['rejection_reason']}")

    if validated:
        print(f"\nValidated memories:")
        for r in validated:
            print(f"  - {r['memory_id']}: {r['validation_runs']} runs, "
                  f"quality={r['quality_score']}, confidence={r['confidence']}")

    # Write output
    output = {
        "version": "1.0",
        "phase": "5.8.2.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "validator.py (Phase 5.8.2.2 Loop Controller)",
        "source_file": CANDIDATES_FILE,
        "summary": {
            "total_candidates_processed": len(candidates),
            "total_memories_evaluated": len(results),
            "validated": len(validated),
            "rejected": len(rejected),
        },
        "results": results,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\nOutput written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()