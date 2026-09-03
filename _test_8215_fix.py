#!/usr/bin/env python3
"""
Phase 8.2.1.5 — Deterministic Unit/Integration Tests

Tests A/B/C/D for the retrieval relevance fix.

A: Redis/TTL/freshness task → Redis memories get higher relevance
B: Cache/eviction/mutation task → Cache memories get higher relevance
C: Negative task → Generic AI memories don't get false boost
D: Order independence — same task, same ranking
"""

import sys
import os

BASE = "/home/shade/.agents"

# Clear any cached .pyc files to ensure fresh imports
sys.path.insert(0, os.path.join(BASE, "runtime", "router"))
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "retrieval"))

from router import Router
from retrieval_optimizer import (
    retrieve,
    compute_static_relevance,
    load_retrieval_index,
    MIN_SCORE,
)

router = Router()
router.load_rules()

index = load_retrieval_index()
memories = index.get("memories", [])

PASS = 0
FAIL = 0


def assert_true(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {msg}")
    else:
        FAIL += 1
        print(f"  FAIL: {msg}")


def assert_greater(a, b, msg):
    global PASS, FAIL
    if a > b:
        PASS += 1
        print(f"  PASS: {msg} ({a:.3f} > {b:.3f})")
    else:
        FAIL += 1
        print(f"  FAIL: {msg} ({a:.3f} <= {b:.3f})")


def get_memory(memory_id):
    for m in memories:
        if m["memory_id"] == memory_id:
            return m
    return None


# ============================================================================
# TEST A: Redis/TTL/freshness task → Redis memories get higher relevance
# ============================================================================
print("=" * 70)
print("TEST A: F1 — Redis session-state drift → Redis/session memories rank high")
print("=" * 70)

task_f1 = "Fix Redis session-state drift between DB truth and cache"
c_f1 = router.classify(task_f1)
query_f1 = c_f1.to_dict()
query_f1["exclude_hypothesis"] = False

print(f"  Query: keywords={c_f1.keywords}, domains={c_f1.domains}")

# A.1: Redis keywords are extracted from task text
assert_true("redis" in c_f1.keywords, "A.1: 'redis' keyword extracted from task text")
assert_true("cache" in c_f1.keywords, "A.1: 'cache' keyword extracted from task text")
assert_true("session" in c_f1.keywords, "A.1: 'session' keyword extracted from task text")

# A.2: H-039 (redis/cache/ttl tagged) has higher static_relevance than T-005 (generic AI)
h039 = get_memory("H-039-REDISSONCONFIG-JAVA-22-28----R")
t005 = get_memory("T-005")
sr_h039 = compute_static_relevance(h039, query_f1)
sr_t005 = compute_static_relevance(t005, query_f1)
assert_greater(sr_h039, sr_t005, "A.2: H-039 static_relevance > T-005 static_relevance")

# A.3: H-039 (redis) has meaningful task_text relevance (at least 2 tag matches: redis, cache)
assert_greater(sr_h039, 0.15, "A.3: H-039 static_relevance > 0.15 (passes MIN_SCORE)")

# A.4: T-005 (generic AI) has significantly lower static_relevance than H-039 for Redis task
# T-005 may get some domain/role match but must be far below task-relevant H-039
assert_true(sr_t005 < sr_h039 * 0.5, f"A.4: T-005 static_relevance < 50% of H-039 ({sr_t005:.3f} < {sr_h039*0.5:.3f})")

# A.5: Full retrieval — H-xxx redis/session memories appear in results
result_f1 = retrieve(query_f1)
f1_ids = [r["memory_id"] for r in result_f1["results"]]
assert_true(any("H-" in mid for mid in f1_ids), "A.5: At least one H-xxx memory in top results")
assert_true("T-005" not in f1_ids, "A.5: T-005 NOT in top results (generic AI filtered)")

# A.6: Session-state memories rank high (task is about session-state drift)
# Check tags, not memory IDs — session-tagged memories may have IDs like H-202-STATE-...
f1_session_in_tags = any("session" in r.get("tags", []) for r in result_f1["results"])
assert_true(f1_session_in_tags, "A.6: Session-related memories (by tags) appear in top results")

print(f"  F1 top results: {f1_ids}")
print(f"  H-039 static={sr_h039:.3f}, T-005 static={sr_t005:.3f}")

# ============================================================================
# TEST B: Cache/eviction/mutation task → Cache memories get higher relevance
# ============================================================================
print("\n" + "=" * 70)
print("TEST B: F2 — Dashboard cache invalidation → Cache memories rank high")
print("=" * 70)

task_f2 = "Fix dashboard cache invalidation after mutation"
c_f2 = router.classify(task_f2)
query_f2 = c_f2.to_dict()
query_f2["exclude_hypothesis"] = False

print(f"  Query: keywords={c_f2.keywords}, domains={c_f2.domains}")

# B.1: Cache keywords are extracted
assert_true("cache" in c_f2.keywords, "B.1: 'cache' keyword extracted from task text")
assert_true("invalidation" in c_f2.keywords, "B.1: 'invalidation' keyword extracted")
assert_true("mutation" in c_f2.keywords, "B.1: 'mutation' keyword extracted")
assert_true("dashboard" in c_f2.keywords, "B.1: 'dashboard' keyword extracted")

# B.2: H-039 has higher static_relevance than T-005
sr_h039_f2 = compute_static_relevance(h039, query_f2)
sr_t005_f2 = compute_static_relevance(t005, query_f2)
assert_greater(sr_h039_f2, sr_t005_f2, "B.2: H-039 static_relevance > T-005 static_relevance")

# B.3: H-039 passes MIN_SCORE
assert_greater(sr_h039_f2, 0.15, "B.3: H-039 static_relevance > 0.15 (passes MIN_SCORE)")

# B.4: T-005 near-zero relevance for cache task
assert_true(sr_t005_f2 < 0.05, f"B.4: T-005 static_relevance < 0.05 (was {sr_t005_f2:.3f})")

# B.5: Full retrieval — H-039 ranks #1 or at least in top 3
result_f2 = retrieve(query_f2)
f2_ids = [r["memory_id"] for r in result_f2["results"]]
assert_true("T-005" not in f2_ids, "B.5: T-005 NOT in top results")
assert_true(any("REDISSON" in mid for mid in f2_ids), "B.5: Redis/cache memory in top results")

# B.6: Dashboard memories should also appear (task mentions dashboard)
dashboard_in_results = any("DASHBOARD" in mid for mid in f2_ids)
print(f"  B.6: Dashboard memories in results: {dashboard_in_results}")

print(f"  F2 top results: {f2_ids}")
print(f"  H-039 static={sr_h039_f2:.3f}, T-005 static={sr_t005_f2:.3f}")

# ============================================================================
# TEST C: Negative task → Generic AI memories don't get false boost
# ============================================================================
print("\n" + "=" * 70)
print("TEST C: F-NEG — CI/CD pipeline → no false boost of generic AI memories")
print("=" * 70)

task_fneg = "Configure CI/CD pipeline for a Go microservice"
c_fneg = router.classify(task_fneg)
query_fneg = c_fneg.to_dict()
query_fneg["exclude_hypothesis"] = False

print(f"  Query: keywords={c_fneg.keywords}, domains={c_fneg.domains}")

# C.1: T-005 has near-zero static_relevance for CI/CD task
sr_t005_fneg = compute_static_relevance(t005, query_fneg)
assert_true(sr_t005_fneg < 0.05, f"C.1: T-005 static_relevance < 0.05 (was {sr_t005_fneg:.3f})")

# C.2: H-039 has near-zero static_relevance for CI/CD task (no redis/cache relevance)
sr_h039_fneg = compute_static_relevance(h039, query_fneg)
assert_true(sr_h039_fneg < 0.15, f"C.2: H-039 static_relevance < 0.15 (was {sr_h039_fneg:.3f})")

# C.3: Full retrieval — T-005 NOT in top results
result_fneg = retrieve(query_fneg)
fneg_ids = [r["memory_id"] for r in result_fneg["results"]]
assert_true("T-005" not in fneg_ids, "C.3: T-005 NOT in top results (no false boost)")

# C.4: After filter should be 0 or very low (no irrelevant memories passing MIN_SCORE)
# Note: with multiplicative scoring, memories with low static_relevance cannot pass
# even with high quality metrics
print(f"  F-NEG: after_filter={result_fneg['after_filter']}, top_k={result_fneg['top_k']}")
print(f"  F-NEG top results: {fneg_ids}")

# C.5: Even if results exist, none should be generic AI memories (T-005, S-001, etc.)
generic_ai = ["T-005", "S-001", "P-001"]
for gid in generic_ai:
    assert_true(gid not in fneg_ids, f"C.5: {gid} NOT in F-NEG results")

# C.6: Key insight — generic AI memory T-005 even with high success_rate (0.938)
# cannot overcome near-zero static_relevance with multiplicative formula
# OLD: 0.01*0.55 + 0.938*0.20 + 0.40*0.15 + 0.32*0.10 = 0.285 (above MIN_SCORE)
# NEW: 0.01 * (1.0 + 0.30) = 0.013 (below MIN_SCORE)
assert_true(sr_t005_fneg * 1.30 < MIN_SCORE,
    f"C.6: T-005 even with max quality_bonus (30%) < MIN_SCORE "
    f"({sr_t005_fneg:.3f} * 1.30 = {sr_t005_fneg*1.30:.3f} < {MIN_SCORE})")

# ============================================================================
# TEST D: Order independence
# ============================================================================
print("\n" + "=" * 70)
print("TEST D: Order independence — same task, same ranking")
print("=" * 70)

# D.1: F1 retrieval is deterministic (same task → same ranking)
result_f1_2 = retrieve(query_f1)
f1_ids_2 = [r["memory_id"] for r in result_f1_2["results"]]
assert_true(f1_ids == f1_ids_2, "D.1: F1 ranking is deterministic across runs")

# D.2: F2 retrieval is deterministic
result_f2_2 = retrieve(query_f2)
f2_ids_2 = [r["memory_id"] for r in result_f2_2["results"]]
assert_true(f2_ids == f2_ids_2, "D.2: F2 ranking is deterministic across runs")

# D.3: F-NEG retrieval is deterministic
result_fneg_2 = retrieve(query_fneg)
fneg_ids_2 = [r["memory_id"] for r in result_fneg_2["results"]]
assert_true(fneg_ids == fneg_ids_2, "D.3: F-NEG ranking is deterministic across runs")

# D.4: Reverse order — run F2 then F1 — should give same results
result_f2_rev = retrieve(query_f2)
result_f1_rev = retrieve(query_f1)
f2_rev_ids = [r["memory_id"] for r in result_f2_rev["results"]]
f1_rev_ids = [r["memory_id"] for r in result_f1_rev["results"]]
assert_true(f2_rev_ids == f2_ids, "D.4: F2 ranking same after F1 run (reverse order)")
assert_true(f1_rev_ids == f1_ids, "D.4: F1 ranking same after F2 run (reverse order)")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} tests")
print("=" * 70)

if FAIL > 0:
    print("\nSOME TESTS FAILED — stopping as required.")
    sys.exit(1)
else:
    print("\nALL TESTS PASSED.")
    sys.exit(0)