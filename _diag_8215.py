#!/usr/bin/env python3
"""Phase 8.2.1.5 Diagnostic: trace exact query generation and retrieval."""
import sys, os, json

BASE = "/home/shade/.agents"

# 1. Router classification
sys.path.insert(0, os.path.join(BASE, "runtime", "router"))
from router import Router

router = Router()
router.load_rules()

# 2. Retrieval
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "retrieval"))
from retrieval_optimizer import retrieve, compute_static_relevance, load_retrieval_index

TASKS = {
    "F1": "Fix Redis session-state drift between DB truth and cache",
    "F2": "Fix dashboard cache invalidation after mutation",
    "F-NEG": "Configure CI/CD pipeline for a Go microservice",
}

print("=" * 80)
print("PHASE 8.2.1.5 DIAGNOSTIC — Query Generation Trace")
print("=" * 80)

for label, task_text in TASKS.items():
    print(f"\n{'─' * 80}")
    print(f"  {label}: {task_text}")
    print(f"{'─' * 80}")

    # Step 1: Router classification
    c = router.classify(task_text)
    print(f"\n  [Router.classify()]")
    print(f"    category:  {c.category}")
    print(f"    domains:   {c.domains}")
    print(f"    roles:     {c.roles}")
    print(f"    keywords:  {c.keywords}")
    print(f"    difficulty: {c.difficulty}")

    query = c.to_dict()
    query["exclude_hypothesis"] = False

    # Step 2: Retrieval
    result = retrieve(query)

    print(f"\n  [Retrieval Results]")
    print(f"    total_considered: {result['total_considered']}")
    print(f"    after_filter:     {result['after_filter']}")
    print(f"    top_k:            {result['top_k']}")
    print()

    for i, r in enumerate(result["results"]):
        print(f"    #{i+1} {r['memory_id']} ({r['type']}/{r['category']})")
        print(f"        final={r['final_score']:.3f}  static={r['static_relevance']:.3f}  succ={r['success_rate']:.3f}  conf={r['confidence_score']:.3f}  perf={r['performance_gain']:.3f}")
        print(f"        tags: {r['tags'][:5]}")

    # Step 3: Check if H-xxx memories with redis/cache tags exist
    index = load_retrieval_index()
    mems = index.get("memories", [])
    redis_mems = [m for m in mems if any("redis" in t.lower() for t in m.get("tags", []))]
    cache_mems = [m for m in mems if any("cache" in t.lower() for t in m.get("tags", []))]
    ttl_mems = [m for m in mems if any("ttl" in t.lower() for t in m.get("tags", []))]
    session_mems = [m for m in mems if any("session" in t.lower() for t in m.get("tags", []))]
    dashboard_mems = [m for m in mems if any("dashboard" in t.lower() for t in m.get("tags", []))]
    invalidation_mems = [m for m in mems if any("invalidation" in t.lower() for t in m.get("tags", []))]

    print(f"\n  [Relevant Memory Inventory]")
    print(f"    redis-tagged:     {len(redis_mems)} ({[m['memory_id'] for m in redis_mems[:5]]})")
    print(f"    cache-tagged:     {len(cache_mems)} ({[m['memory_id'] for m in cache_mems[:5]]})")
    print(f"    ttl-tagged:       {len(ttl_mems)} ({[m['memory_id'] for m in ttl_mems[:5]]})")
    print(f"    session-tagged:   {len(session_mems)} ({[m['memory_id'] for m in session_mems[:5]]})")
    print(f"    dashboard-tagged: {len(dashboard_mems)} ({[m['memory_id'] for m in dashboard_mems[:5]]})")
    print(f"    invalidation:     {len(invalidation_mems)} ({[m['memory_id'] for m in invalidation_mems[:5]]})")

    # Step 4: Show why a redis memory didn't make it
    if redis_mems:
        sample = redis_mems[0]
        print(f"\n  [Why {sample['memory_id']} didn't rank]")
        print(f"    tags:    {sample.get('tags', [])}")
        print(f"    roles:   {sample.get('roles', [])}")
        print(f"    category: {sample.get('category', '')}")
        sr = compute_static_relevance(sample, query)
        print(f"    static_relevance: {sr}")
        print(f"    query domains: {query['domains']}")
        print(f"    query keywords: {query['keywords']}")
        print(f"    query roles: {query['roles']}")
        print(f"    → domain match: 'redis' in tags? {'redis' in [t.lower() for t in sample.get('tags', [])]}")
        print(f"    → domain match: 'database' in category? {'database' in sample.get('category', '').lower()}")
        print(f"    → keyword match: 'redis' in query keywords? {'redis' in [k.lower() for k in query['keywords']]}")
        print(f"    → keyword match: 'cache' in query keywords? {'cache' in [k.lower() for k in query['keywords']]}")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)