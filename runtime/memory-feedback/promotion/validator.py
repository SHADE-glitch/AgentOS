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
import sys
from datetime import datetime, timezone
from collections import defaultdict

BASE = "/home/shade/.agents/runtime/memory-feedback"
CANDIDATES_FILE = os.path.join(BASE, "memory-candidates.yaml")
OUTPUT_FILE = os.path.join(BASE, "promotion", "validation-results.yaml")
MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"

# Phase 8.6-C5: Import shared helpers from collector
_COLLECTOR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "collector")
if _COLLECTOR_DIR not in sys.path:
    sys.path.insert(0, _COLLECTOR_DIR)
from collector import (
    HYPOTHESIS_CANDIDATE_TYPES,
    is_countable_observation,
    canonical_source_for,
)

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
        ctype = c.get("candidate_type", "")
        is_hyp = mid.upper().startswith("H-")

        # Phase 8.6-C3: Fail-closed type guard — reject cross-type contamination
        if is_hyp and ctype == "reinforce":
            # reinforce targeting H-xxx is type confusion; add to group but mark rejected
            c["_rejected"] = True
            c["_rejection_reason"] = (
                "Type confusion: reinforce targeting H-xxx "
                "(expected reinforce_hypothesis)")
        elif not is_hyp and ctype in HYPOTHESIS_CANDIDATE_TYPES:
            c["_rejected"] = True
            c["_rejection_reason"] = (
                "Type confusion: reinforce_hypothesis/weaken_hypothesis "
                "targeting non-H memory")

        groups[mid]["memory_id"] = mid
        groups[mid]["candidates"].append(c)

        # Phase 8.6-C3: skip execution counting for rejected candidates
        if c.get("_rejected"):
            # Still add to quality scores for audit
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
            continue

        # Phase 8.6-C5: use shared is_countable_observation() gate
        # (I7 inconclusive + I9 self-confirm)
        if is_countable_observation(c):
            # Phase 8.6-C4: hypothesis lane uses canonical_source for counting
            if is_hyp:
                cs = canonical_source_for(c)
                if cs:
                    # Phase 8.7 I10/I11 second-level dedup (hypothesis lane only)
                    _root = c.get("root_task_id") or c.get("hypothesis_engagement", {}).get("root_task_id", "") or ""
                    _model = c.get("model_family") or c.get("hypothesis_engagement", {}).get("model_family", "unknown") or "unknown"
                    _rctx = c.get("retrieval_context_hash") or c.get("hypothesis_engagement", {}).get("retrieval_context_hash", "") or ""
                    # lazy init dedup sets per memory
                    if "seen_root_tasks" not in groups[mid]:
                        groups[mid]["seen_root_tasks"] = set()
                        groups[mid]["seen_model_contexts"] = set()
                    seen_roots = groups[mid]["seen_root_tasks"]
                    seen_ctx = groups[mid]["seen_model_contexts"]
                    _is_root_dup = bool(_root and _root in seen_roots)
                    _is_ctx_dup = bool((_model != "unknown" or _rctx != "") and (_model, _rctx) in seen_ctx)
                    if _is_root_dup or _is_ctx_dup:
                        pass  # collapsed by I10 or I11 — do not count as new execution
                    else:
                        groups[mid]["executions"].add(cs)
                        if _root:
                            seen_roots.add(_root)
                        if _model != "unknown" or _rctx != "":
                            seen_ctx.add((_model, _rctx))
            else:
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

    Phase 8.6-C2: Hypothesis validated requires 2 distinct canonical_source loops.
    Phase 8.6-C3: Type-confused candidates rejected fail-closed.
    """
    validation_runs = len(group["executions"])
    best_qs = group["best_quality"]
    ctype = group["candidates"][0].get("candidate_type", "") if group["candidates"] else ""
    is_hypothesis = memory_id.upper().startswith("H-")

    # Phase 8.7 I12: negative evidence (non-countable) preserved
    # Use explicit countable flag if present, else fallback to is_countable_observation
    def _is_neg(c):
        if "countable" in c:
            return not c.get("countable", True)
        return not is_countable_observation(c)
    negative_evidence_count = sum(1 for c in group.get("candidates", []) if _is_neg(c))
    # Also count non-countable observations from observation log enrichment if stored
    # (enrich_groups will have already added to candidates? but we keep simple)
    counter_evidence_ratio = validation_runs / max(validation_runs + negative_evidence_count, 1)
    group["_negative_evidence_count"] = negative_evidence_count
    group["_counter_evidence_ratio"] = counter_evidence_ratio
    # capture env_fingerprint from first countable candidate
    _env_fp = {}
    for c in group.get("candidates", []):
        # find first countable with env_fingerprint
        _cand_fp = c.get("env_fingerprint") or c.get("evidence", {}).get("env_fingerprint") or {}
        if _cand_fp:
            _env_fp = _cand_fp
            break
    group["_env_fingerprint"] = _env_fp
    # Phase 8.7 I10/I11/I13: evidence independence audit
    _roots = sorted({c.get("root_task_id") or c.get("hypothesis_engagement", {}).get("root_task_id", "") or "" for c in group.get("candidates", []) if c.get("root_task_id") or c.get("hypothesis_engagement", {}).get("root_task_id")})
    _roots = [r for r in _roots if r]
    _models = sorted({c.get("model_family") or c.get("hypothesis_engagement", {}).get("model_family", "") or "unknown" for c in group.get("candidates", [])})
    _models = [m for m in _models if m and m != "unknown"] or (["unknown"] if _models else [])
    _ctxs = sorted({c.get("retrieval_context_hash") or c.get("hypothesis_engagement", {}).get("retrieval_context_hash", "") or "" for c in group.get("candidates", []) if c.get("retrieval_context_hash") or c.get("hypothesis_engagement", {}).get("retrieval_context_hash")})
    _ctxs = [x for x in _ctxs if x]
    group["_evidence_independence"] = {"root_task_ids": _roots, "model_families": _models, "context_hashes": _ctxs}
    # Phase 8.7 I16: staleness warning — compare env_fingerprint with previous (if available)
    # For now, if multiple distinct env fingerprints observed, warn. Simple audit.
    _env_fps = set()
    for c in group.get("candidates", []):
        fp = c.get("env_fingerprint") or c.get("evidence", {}).get("env_fingerprint") or {}
        if fp:
            # hashable representation
            try:
                _env_fps.add(str(sorted(fp.items())))
            except Exception:
                _env_fps.add(str(fp))
    if len(_env_fps) > 1:
        group["_staleness_warning"] = True
        group["_staleness_detail"] = f"env_fingerprint changed across {len(_env_fps)} observations"
    else:
        group["_staleness_warning"] = False
        group["_staleness_detail"] = ""

    # Phase 8.6-C3: Check for type-confused candidates rejected at group stage
    rejected_candidates = [c for c in group.get("candidates", []) if c.get("_rejected")]
    if rejected_candidates:
        status = "rejected"
        rejection_reason = rejected_candidates[0].get("_rejection_reason",
                                                       "Type confusion rejected")
        # Build result with the rejection info
        return _build_result(status, memory_id, group, validation_runs, best_qs,
                             ctype, is_hypothesis, rejection_reason)

    # Phase 8.6-C2: hypothesis validated requires 2 distinct canonical_source loops
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
    elif ctype in ("weaken", "weaken_hypothesis"):
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

    return _build_result(status, memory_id, group, validation_runs, best_qs,
                         ctype, is_hypothesis, rejection_reason)


def _build_result(status, memory_id, group, validation_runs, best_qs,
                  ctype, is_hypothesis, rejection_reason):
    """Build the result dict for validate_memory_group (Phase 8.6 refactor)."""
    # Calculate confidence — Phase 8.7 I14: cap hypothesis lane at 2 observations
    if is_hypothesis:
        confidence = min(min(validation_runs, 2) / MAX_OBSERVATIONS_FOR_FULL_CONFIDENCE, 1.0)
    else:
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
            # Phase 8.6-C3: preserve C3 type-confusion rejection reason
            if not rejection_reason or "Type confusion" not in str(rejection_reason):
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
        "checks": {
            "is_real_execution": len(group["all_session_ids"]) > 0,
            "has_execution_evidence": len(group["all_output_hashes"]) > 0,
            "has_independent_verification": validation_runs >= (
                HYPOTHESIS_MIN_OBSERVATIONS if is_hypothesis else MIN_OBSERVATIONS),
            "quality_above_threshold": best_qs >= QUALITY_THRESHOLD,
            "not_hypothesis": ctype != "create_hypothesis" and not is_hypothesis,
        },
        "rejection_reason": rejection_reason,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        **({"cross_loop": {
            "prior_observations": group["cross_loop_observations"],
            "sources": group.get("cross_loop_sources", []),
        }} if group.get("cross_loop_observations") else {}),
        # Phase 8.7 I12/I16 audit fields
        "negative_evidence_count": group.get("_negative_evidence_count", 0),
        "counter_evidence_ratio": round(group.get("_counter_evidence_ratio", 1.0), 2),
        "env_fingerprint": group.get("_env_fingerprint", {}),
        "staleness_warning": group.get("_staleness_warning", False),
        "staleness_detail": group.get("_staleness_detail", ""),
        "evidence_independence": group.get("_evidence_independence", {"root_task_ids": [], "model_families": [], "context_hashes": []}),
        "observation_id": (group.get("candidates", [{}])[0].get("observation_id") or group.get("candidates", [{}])[0].get("hypothesis_engagement", {}).get("observation_id", "") or "") if group.get("candidates") else "",
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

    Phase 8.6-C4/C5: Uses canonical_source for hypothesis lane counting;
    filters out non-countable log entries (I7 inconclusive + I9 self-confirm).

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
        # Phase 8.7: init dedup sets from existing group (reuse same sets)
        if "seen_root_tasks" not in group:
            group["seen_root_tasks"] = set()
            group["seen_model_contexts"] = set()
        for obs in log_obs:
            # Phase 8.7: read countable flag; backward compat fallback to old checks
            if "countable" in obs:
                if not obs.get("countable", True):
                    continue
            else:
                # backward compat: old log entries without countable
                if obs.get("same_loop_as_creation"):
                    continue
                if obs.get("candidate_type") in HYPOTHESIS_CANDIDATE_TYPES \
                   and obs.get("outcome") == "inconclusive":
                    continue

            # Phase 8.6-C4: prefer canonical_source for hypothesis lane
            source = obs.get("canonical_source") or obs.get("source_loop")
            if source:
                # Phase 8.7 I10/I11 dedup for log-derived observations
                _r = obs.get("root_task_id") or ""
                _m = obs.get("model_family") or "unknown"
                _ctx = obs.get("retrieval_context_hash") or ""
                _is_root_dup = bool(_r and _r in group["seen_root_tasks"])
                _is_ctx_dup = bool((_m != "unknown" or _ctx != "") and (_m, _ctx) in group["seen_model_contexts"])
                if _is_root_dup or _is_ctx_dup:
                    pass
                elif source not in group["executions"]:
                    group["executions"].add(source)
                    cross_loop_sources.append(source)
                    if _r:
                        group["seen_root_tasks"].add(_r)
                    if _m != "unknown" or _ctx != "":
                        group["seen_model_contexts"].add((_m, _ctx))

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

        # Phase 8.7 I10/I11 dedup sets for synthesized group
        _syn_seen_roots = set()
        _syn_seen_ctx = set()
        for obs in mem_obs:
            # Phase 8.7: countable flag
            if "countable" in obs:
                if not obs.get("countable", True):
                    continue
            else:
                if obs.get("same_loop_as_creation"):
                    continue
                if obs.get("candidate_type") in HYPOTHESIS_CANDIDATE_TYPES \
                   and obs.get("outcome") == "inconclusive":
                    continue

            # Phase 8.6-C4: prefer canonical_source for hypothesis lane
            sl = obs.get("canonical_source") or obs.get("source_loop")
            if sl:
                _r = obs.get("root_task_id") or ""
                _m = obs.get("model_family") or "unknown"
                _ctx = obs.get("retrieval_context_hash") or ""
                _is_root_dup = bool(_r and _r in _syn_seen_roots)
                _is_ctx_dup = bool((_m != "unknown" or _ctx != "") and (_m, _ctx) in _syn_seen_ctx)
                if _is_root_dup or _is_ctx_dup:
                    pass
                else:
                    executions.add(sl)
                    if _r:
                        _syn_seen_roots.add(_r)
                    if _m != "unknown" or _ctx != "":
                        _syn_seen_ctx.add((_m, _ctx))

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


def validate_candidates(candidates, quiet=False, loop_id=None):
    """
    Validate a list of candidates directly (programmatic entry point).
    Phase 5.8.2.2: Added for loop controller integration.
    Phase 8.3: loop_id added for artifact authority.

    Args:
        candidates: list of candidate dicts from collector
        quiet: suppress console output
        loop_id: optional str, for artifact authority tracing

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
        if loop_id:
            result["loop_id"] = loop_id
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