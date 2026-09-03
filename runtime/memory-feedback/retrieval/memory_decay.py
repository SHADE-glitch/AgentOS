#!/usr/bin/env python3
"""
Memory Decay System — Phase 5.8
Implements decay-policy.yaml to gradually reduce retrieval weight
of unused or underperforming memories.

CRITICAL: Never deletes memories. Only modifies decay_factor.
States: active → degraded → archived_candidate (reversible)
"""

import yaml
import os
from datetime import datetime, timezone, timedelta

# Paths
RETRIEVAL_INDEX = "/home/shade/.agents/memory/retrieval-index.yaml"
USAGE_DATA = "/home/shade/.agents/runtime/memory-feedback/retrieval/retrieval-history.yaml"
PERF_DATA = "/home/shade/.agents/runtime/memory-feedback/evaluation/effectiveness-results.yaml"
DECAY_STATE = "/home/shade/.agents/runtime/memory-feedback/retrieval/decay-state.yaml"
DECAY_LOG = "/home/shade/.agents/runtime/memory-feedback/retrieval/decay-log.yaml"


def load_yaml(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath) as f:
        return yaml.unsafe_load(f)


def load_usage_data():
    """Extract per-memory usage statistics from retrieval history and traces."""
    # From retrieval history
    history = load_yaml(USAGE_DATA)
    retrievals = history.get("retrievals", [])

    # From effectiveness results (raw trace data)
    perf = load_yaml(PERF_DATA)
    raw_metrics = perf.get("raw_data", {}).get("trace_metrics", [])

    usage = {}
    now = datetime.now(timezone.utc)

    # Build from trace data
    for m in raw_metrics:
        mids = m.get("memories_used", [])
        for mid in mids:
            if mid not in usage:
                usage[mid] = {
                    "usage_count": 0,
                    "successful_uses": 0,
                    "last_used": None,
                    "quality_scores": [],
                }
            usage[mid]["usage_count"] += 1
            if m.get("status") == "success":
                usage[mid]["successful_uses"] += 1
            usage[mid]["quality_scores"].append(m.get("quality_score", 0))

    # Build from retrieval history
    for entry in retrievals:
        for mid in entry.get("retrieved_memories", []):
            if mid not in usage:
                usage[mid] = {
                    "usage_count": 0,
                    "successful_uses": 0,
                    "last_retrieved": None,
                    "quality_scores": [],
                }
            ts = entry.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    if usage[mid].get("last_retrieved") is None or dt > datetime.fromisoformat(usage[mid]["last_retrieved"]):
                        usage[mid]["last_retrieved"] = ts
                except (ValueError, TypeError):
                    pass

    # Compute success rates
    for mid, data in usage.items():
        uc = data["usage_count"]
        data["success_rate"] = data["successful_uses"] / uc if uc > 0 else 0.5

    return usage


def compute_decay_factor(memory, usage_data, perf_data):
    """
    Compute decay factor for a single memory.
    Returns (decay_factor, reasons, state).
    """
    memory_id = memory["memory_id"]
    usage = usage_data.get(memory_id, {})
    uc = usage.get("usage_count", 0)
    success_rate = usage.get("success_rate", 0.5)
    observation_count = memory.get("observation_count", 0)
    mem_type = memory.get("type", "unknown")
    created_at = memory.get("created_at", "")

    factors = []
    reasons = []

    # --- Trigger 1: Unused decay ---
    last_used = usage.get("last_used")
    last_retrieved = usage.get("last_retrieved")
    last_activity = last_used or last_retrieved

    if uc == 0:
        # Never used — check creation date
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
                days_since = (datetime.now(timezone.utc) - created_dt).days
                if days_since >= 90:
                    factors.append(0.5)
                    reasons.append(f"unused_severe: {days_since}d since creation")
                elif days_since >= 60:
                    factors.append(0.7)
                    reasons.append(f"unused_moderate: {days_since}d since creation")
                elif days_since >= 30:
                    factors.append(0.9)
                    reasons.append(f"unused_mild: {days_since}d since creation")
            except (ValueError, TypeError):
                pass
        else:
            factors.append(0.9)
            reasons.append("unused: no usage data")
    elif last_activity:
        try:
            last_dt = datetime.fromisoformat(last_activity)
            days_since = (datetime.now(timezone.utc) - last_dt).days
            if days_since >= 90:
                factors.append(0.5)
                reasons.append(f"unused_severe: {days_since}d since last activity")
            elif days_since >= 60:
                factors.append(0.7)
                reasons.append(f"unused_moderate: {days_since}d since last activity")
            elif days_since >= 30:
                factors.append(0.9)
                reasons.append(f"unused_mild: {days_since}d since last activity")
        except (ValueError, TypeError):
            pass

    # --- Trigger 2: Low success rate ---
    if uc >= 3:  # At least 3 uses before this applies
        if success_rate < 0.2:
            factors.append(0.5)
            reasons.append(f"low_success_severe: {success_rate}")
        elif success_rate < 0.4:
            factors.append(0.7)
            reasons.append(f"low_success_moderate: {success_rate}")
        elif success_rate < 0.6:
            factors.append(0.9)
            reasons.append(f"low_success_mild: {success_rate}")

    # --- Trigger 3: Low confidence ---
    if observation_count == 0:
        factors.append(0.85)
        reasons.append("low_confidence: 0 observations")
    elif observation_count == 1:
        factors.append(0.90)
        reasons.append("low_confidence: 1 observation")

    # --- Trigger 4: Hypothesis protection ---
    if mem_type == "hypothesis":
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
                days_since = (datetime.now(timezone.utc) - created_dt).days
                if days_since > 7:
                    factors.append(0.7)
                    reasons.append(f"hypothesis: {days_since}d old (decay after 7d)")
            except (ValueError, TypeError):
                factors.append(0.7)
                reasons.append("hypothesis: default decay")
        else:
            factors.append(0.7)
            reasons.append("hypothesis: default decay")

    # --- Trigger 5: Low performance ---
    if uc >= 2:
        quality_scores = usage.get("quality_scores", [])
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        # Compare to global average
        all_qualities = []
        for mdata in usage_data.values():
            all_qualities.extend(mdata.get("quality_scores", []))
        global_avg = sum(all_qualities) / len(all_qualities) if all_qualities else 0

        if global_avg > 0:
            perf_ratio = avg_quality / global_avg
            if perf_ratio < 0.5:
                factors.append(0.7)
                reasons.append(f"low_performance: avg_quality={avg_quality:.2f} vs global={global_avg:.2f}")
            elif perf_ratio < 0.8:
                factors.append(0.85)
                reasons.append(f"low_performance_mild: avg_quality={avg_quality:.2f} vs global={global_avg:.2f}")

    # --- Final decay factor ---
    decay_factor = min(factors) if factors else 1.0

    # --- Determine state ---
    if decay_factor >= 0.9:
        state = "active"
    elif decay_factor >= 0.5:
        state = "degraded"
    else:
        state = "archived_candidate"

    return {
        "memory_id": memory_id,
        "decay_factor": round(decay_factor, 3),
        "state": state,
        "reasons": reasons,
        "usage_count": uc,
        "success_rate": round(success_rate, 3),
        "observation_count": observation_count,
    }


def reconcile_before_decay():
    """
    Phase 5.8.1: Reconcile retrieval-index against canonical .md files before decay.
    Returns True if index is consistent, False if inconsistency detected.
    """
    import subprocess
    import sys

    reconciler = os.path.join(
        os.path.dirname(__file__), "memory_state_reconciler.py"
    )
    if not os.path.exists(reconciler):
        print("WARNING: memory_state_reconciler.py not found — skip reconciliation", file=sys.stderr)
        return True

    print("Phase 5.8.1: Checking state consistency before decay...", file=sys.stderr)
    result = subprocess.run(
        ["python3", reconciler, "--check"],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        print("  State consistency: CONSISTENT", file=sys.stderr)
        return True

    print("\n" + "!" * 60, file=sys.stderr)
    print("MEMORY_STATE_INCONSISTENCY", file=sys.stderr)
    print("!" * 60, file=sys.stderr)
    print(result.stdout.strip(), file=sys.stderr)
    print("!" * 60, file=sys.stderr)
    print("\nDecay aborted. Run memory_state_reconciler.py --repair first.", file=sys.stderr)
    return False


def compute_all_decay():
    """Compute decay factors for all memories."""
    # Phase 5.8.1: Reconcile before decay
    if not reconcile_before_decay():
        return None

    index = load_yaml(RETRIEVAL_INDEX)
    memories = index.get("memories", [])
    usage_data = load_usage_data()
    perf_data = load_yaml(PERF_DATA)

    results = []
    for mem in memories:
        result = compute_decay_factor(mem, usage_data, perf_data)
        results.append(result)

    # Summary
    active = [r for r in results if r["state"] == "active"]
    degraded = [r for r in results if r["state"] == "degraded"]
    archived = [r for r in results if r["state"] == "archived_candidate"]

    output = {
        "version": "1.0",
        "phase": "5.8",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_memories": len(results),
            "active": len(active),
            "degraded": len(degraded),
            "archived_candidate": len(archived),
        },
        "memories": results,
    }

    # Save
    os.makedirs(os.path.dirname(DECAY_STATE), exist_ok=True)
    with open(DECAY_STATE, "w") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Save log
    log = load_yaml(DECAY_LOG)
    if not log:
        log = {"version": "1.0", "phase": "5.8", "cycles": []}
    cycle_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": output["summary"],
        "decayed": [r for r in results if r["decay_factor"] < 1.0],
    }
    log["cycles"].append(cycle_entry)

    with open(DECAY_LOG, "w") as f:
        yaml.dump(log, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return output


def get_decay_factors():
    """Return a dict of memory_id -> decay_factor for use by retrieval_optimizer."""
    state = load_yaml(DECAY_STATE)
    if not state:
        return {}
    return {m["memory_id"]: m["decay_factor"] for m in state.get("memories", [])}


def main():
    print("=" * 60)
    print("Phase 5.8 — Memory Decay System")
    print("=" * 60)

    result = compute_all_decay()

    if result is None:
        print("\nDecay cycle terminated due to state inconsistency.")
        return

    print(f"\nTotal memories: {result['summary']['total_memories']}")
    print(f"  active:              {result['summary']['active']}")
    print(f"  degraded:            {result['summary']['degraded']}")
    print(f"  archived_candidate:  {result['summary']['archived_candidate']}")

    print("\n--- Decayed Memories ---")
    for m in result["memories"]:
        if m["decay_factor"] < 1.0:
            print(f"  {m['memory_id']}: decay={m['decay_factor']}, state={m['state']}")
            for reason in m["reasons"]:
                print(f"    → {reason}")

    print(f"\nDecay state saved to: {DECAY_STATE}")
    print(f"Decay log saved to: {DECAY_LOG}")


if __name__ == "__main__":
    main()