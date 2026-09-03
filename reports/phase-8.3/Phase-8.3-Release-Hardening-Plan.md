# Phase 8.3 Release Hardening Plan

**Author:** Agent OS Release Hardening Engineer
**Date:** 2026-09-03
**Status:** AWAITING REVIEW — Do not implement until approved

---

## Executive Summary

Phase 8.2.1 proved the individual components of the Memory Feedback Loop work. But the end-to-end learning loop — **Run 1 → Memory → Run 2 → Retrieval → Influence → Validation → Promotion** — has not been demonstrated as a closed circuit. Five structural gaps prevent the system from being a verifiable, auditable, repeatable closed loop.

This plan identifies the root cause of each gap and proposes minimal, non-invasive fixes. No new features. No benchmark changes. No scoring changes. Just hardening the existing loop.

---

## 1. Artifact Authority

### Root Cause

The five runtime artifacts that constitute the learning loop lineage have no unified identifier:

| Artifact | Has loop_id? | Has timestamp? | Writable from pipeline? |
|---|---|---|---|
| `loop_state.yaml` (per-loop) | Yes (filename) | Yes | Yes |
| `retrieval-history.yaml` | **No** | Yes | Yes |
| `memory-candidates.yaml` | **No** | Yes | Yes |
| `validation-results.yaml` | **No** | Yes | Yes |
| `promotion-results.yaml` | **No** | Yes | Yes |

The `save_retrieval_history()` function in [retrieval_optimizer.py](file:///home/shade/.agents/runtime/memory-feedback/retrieval/retrieval_optimizer.py#L480-L494) writes:
```yaml
- timestamp: '2026-08-30T...'
  query: {...}
  retrieved_memories: [...]
```
No `loop_id`. No `execution_id`. The retrieval_history entry is untraceable to the loop that produced it.

The `collector_state.yaml` uses `trace_id` (execution_id), not `loop_id`. The `memory-candidates.yaml` has `source_executions` but these are EXEC-xxx not LOOP-xxx.

### Architecture Impact

**Low.** All artifacts are already written within the loop controller pipeline. The `loop_id` is available at every stage. The fix is to pass it to the functions that write artifacts.

### Minimal Implementation

**File: `retrieval_adapter.py`** — Pass `loop_id` through to `save_retrieval_history()`:

1. Change `adapt()` signature to accept `loop_id` parameter (default `None` for backward compat)
2. Pass `loop_id` to `save_retrieval_history(query, raw_result, loop_id=loop_id)`

**File: `retrieval_optimizer.py`** — Accept and store `loop_id`:

```python
def save_retrieval_history(query, result, loop_id=None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "loop_id": loop_id or "unknown",
        "query": query,
        "retrieved_memories": [...],
    }
```

**File: `loop_controller.py`** — Pass `loop_id` to `retrieval_adapt()`:

```python
decision_context = retrieval_adapt(task_id, task_text, memory_mode, loop_id=loop_id)
```

**File: `promoter.py`** — Add `loop_id` to validation-results and promotion-results:

```python
# In validate_candidates() output:
"loop_id": loop_id,  # added

# In promote_validated() output:
"loop_id": loop_id,  # added
```

**File: `collector.py`** — Add `loop_id` to candidate entries:

```python
"loop_id": loop_id,  # added to each candidate
```

### Frozen Surfaces

- `retrieval_optimizer.retrieve()` interface unchanged (loop_id is added to history, not retrieval)
- `retrieval_adapter.adapt()` adds optional parameter, backward compatible
- All existing readers of these artifacts ignore unknown fields

### Tests Required

- `test_artifact_authority.py`: Verify every artifact written by a loop contains `loop_id`
- `test_artifact_lineage.py`: Verify `loop_id` is consistent across all artifacts from the same loop

---

## 2. Cross-loop Memory Lineage

### Root Cause

The system creates hypotheses (H-xxx) in the retrieval index, but there is no mechanism to verify that a hypothesis created in Run 1 is retrievable in Run 2 for the same or similar task.

The retrieval index is updated by the promoter, which writes `observation_count` and `status` fields. But Run 2's retrieval only reads the index — it has no "did we just create this?" awareness.

The gap is not in retrieval logic — it's in **verification**. There is no deterministic test that simulates:
```
Run 1: create H-xxx → index updated
Run 2: same task → retrieval_optimizer.retrieve() → H-xxx in results
```

### Architecture Impact

**Low.** This is a verification gap, not a code gap. The retrieval pipeline already reads from the index. The fix is to add a deterministic test that writes to the index, then reads from it.

### Minimal Implementation

**File: `tests/test_cross_loop_lineage.py`** (new):

```python
def test_run1_hypothesis_retrievable_in_run2():
    """Run 1: create H-xxx. Run 2: same task → H-xxx appears in retrieval."""
    # 1. Inject a hypothesis into the index (simulating Run 1 promotion)
    index = load_retrieval_index()
    hyp = {
        "memory_id": "H-TEST-CROSS-LOOP",
        "type": "hypothesis",
        "category": "backend",
        "tags": ["redis", "cache", "TTL", "staleness"],
        "roles": ["database-engineer"],
        "evidence_level": "hypothesis",
        "confidence": "low",
        "observation_count": 1,
        "status": "hypothesis",
    }
    index["memories"].append(hyp)
    # Save temporarily
    # ...
    
    # 2. Run retrieval with a task that matches the hypothesis domain
    query = {
        "task_text": "dashboard aggregates are cached in Redis with a TTL",
        "category": "backend",
        "domains": ["redis", "cache"],
        "roles": ["database-engineer"],
        "keywords": ["redis", "TTL", "cache", "staleness"],
        "difficulty": "medium",
    }
    result = retrieve(query)
    
    # 3. Verify H-TEST-CROSS-LOOP appears in results
    retrieved_ids = [r["memory_id"] for r in result["results"]]
    assert "H-TEST-CROSS-LOOP" in retrieved_ids, \
        f"Run 2 retrieval did not find Run 1 hypothesis. Retrieved: {retrieved_ids}"
    
    # 4. Cleanup: remove from index
```

**Note:** This test must:
- Use a temporary copy of the index (not modify the real one)
- Verify the hypothesis is in the top-K results
- Clean up after itself

### Frozen Surfaces

- `retrieval_optimizer.retrieve()` — unchanged
- `retrieval-index.yaml` — temporarily modified in test, restored after
- All artifacts — unchanged

### Tests Required

- `test_A_cross_loop_retrieval`: Hypothesis created in Run 1 → retrievable in Run 2
- `test_B_same_task_same_result`: Same task run twice → same hypothesis retrieved both times
- `test_C_different_task_no_false_positive`: Unrelated task → hypothesis NOT retrieved

---

## 3. Hypothesis Retrieval Priority

### Root Cause

The multiplicative scoring formula structurally disadvantages hypotheses:

```
final = static_relevance * (1.0 + quality_bonus)

quality_bonus = success_rate * 0.15 + confidence_score * 0.10 + performance_gain * 0.05
```

For a typical established memory:
- `static_relevance` = 0.33 (good tag match)
- `usage_count` = 5, `successful_uses` = 4 → `success_rate` = 0.80
- `observation_count` = 2 → `confidence` = 0.40
- `quality_bonus` = 0.80 × 0.15 + 0.40 × 0.10 + 0 × 0.05 = 0.16
- `final` = 0.33 × 1.16 = **0.383**

For a typical hypothesis:
- `static_relevance` = 0.28 (same tag match, but no task_text_score boost because hypothesis tags are auto-generated code fragments)
- `usage_count` = 0 → `success_rate` = 0.50 (fallback)
- `observation_count` = 1 → `confidence` = 0.20
- `quality_bonus` = 0.50 × 0.15 + 0.20 × 0.10 + 0 × 0.05 = 0.095
- `final` = 0.28 × 1.095 = **0.307**

The hypothesis loses because:
1. **Lower static_relevance** — hypothesis tags are auto-generated code fragments (e.g., `REDISSONCONFIG`, `JAVA-22-28`), which don't match natural language task text as well as curated tags (e.g., `redis`, `cache`, `TTL`)
2. **Lower quality_bonus** — hypotheses have zero usage history by definition

**This is a structural problem, not a bug.** The multiplicative formula is correct for established memories. But it creates a chicken-and-egg problem: hypotheses need to be retrieved to be used, but they need usage to be retrieved.

### Architecture Impact

**Medium.** The fix must preserve the trust boundary (hypothesis != established) while allowing task-relevant hypotheses to be retrieved.

### Design Principle

**Do not boost hypothesis scores.** Instead, introduce a **separate hypothesis retrieval lane** that operates alongside established memory retrieval but does not mix scores.

The current design already separates hypotheses from established memories in the retrieval adapter:
```python
# retrieval_adapter.py: separate memories and hypotheses
for r in raw_result.get("results", []):
    if r.get("is_hypothesis") or r.get("type") == "hypothesis":
        hypotheses.append(r)
    else:
        memories.append(r)
```

The fix: in `retrieve()`, run a **two-pass retrieval**:
1. Pass 1: Rank established memories (unchanged, multiplicative formula)
2. Pass 2: Rank hypotheses by **static_relevance only** (no quality_bonus, since they have no quality history)

Then return both lists, keeping the top-5 established + top-5 hypotheses.

### Minimal Implementation

**File: `retrieval_optimizer.py`** — Two-pass retrieval in `retrieve()`:

```python
def retrieve(query, decay_factors=None):
    # ... existing code ...
    
    # Pass 1: Established memories (unchanged)
    established_results = []
    hypothesis_results = []
    
    for mem in memories:
        # ... existing scoring ...
        result = compute_adaptive_score(mem, static_relevance, usage_data, eval_data, decay)
        
        if mem.get("type") == "hypothesis":
            # Hypotheses: use static_relevance only, no quality_bonus
            # (they have no quality history to draw from)
            result["final_score"] = result["static_relevance"]
            hypothesis_results.append(result)
        else:
            established_results.append(result)
    
    # Sort each lane independently
    established_results.sort(key=lambda r: r["final_score"], reverse=True)
    hypothesis_results.sort(key=lambda r: r["final_score"], reverse=True)
    
    # Return top-K from each lane
    return {
        "results": established_results[:TOP_K] + hypothesis_results[:TOP_K],
        "established_results": established_results[:TOP_K],
        "hypothesis_results": hypothesis_results[:TOP_K],
        ...
    }
```

**Key invariant preserved:** Hypotheses are still labeled `"is_hypothesis": true`, `"warning": "Unvalidated hypothesis..."`, and separated in the injection prompt with `[UNVALIDATED]` prefix. The trust boundary is maintained.

### Frozen Surfaces

- `retrieval_optimizer.retrieve()` return format — `results` field still contains all ranked memories. New fields `established_results` and `hypothesis_results` are additive.
- `retrieval_adapter.adapt()` — unchanged. It already separates hypotheses from memories.
- `aos_host_adapter.py` — unchanged. It already separates hypotheses in injection.
- Agent prompt — unchanged. Hypotheses still labeled `[UNVALIDATED]`.
- Scoring rubric — unchanged.

### Tests Required

- `test_hypothesis_retrieval_lane`: Hypothesis with high static_relevance but no usage → appears in hypothesis_results
- `test_established_memory_lane_unchanged`: Established memory ranking unchanged
- `test_hypothesis_not_outrank_established`: Hypothesis score is never compared to established score
- `test_trust_boundary_preserved`: Hypothesis still has `is_hypothesis: true` and warning label

---

## 4. Validation Aggregation

### Root Cause

The observation log (`memory-observation-log.yaml`) has only 2 entries, both for H-096. The validator reads from `memory-candidates.yaml`, which is generated per-run by the collector. Each run overwrites candidates, so the validator never sees cross-run evidence.

The flow is:
```
Run 1: Collector → memory-candidates.yaml (overwritten each cycle)
Run 1: Validator → validation-results.yaml (reads from candidates.yaml)
Run 2: Collector → memory-candidates.yaml (overwritten)
Run 2: Validator → validation-results.yaml (no memory of Run 1)
```

The `observation_count` in `retrieval-index.yaml` is only updated by the promoter, which requires validation first. But validation requires `observation_count >= 2`. This is a deadlock: hypotheses can't be validated because they have 1 observation, but they can't get a second observation because the observation log isn't populated.

The validator's `group_candidates_by_memory()` groups by memory_id within a single candidate file. It doesn't read the observation log at all.

### Architecture Impact

**Medium.** The fix requires the observation log to be populated from the collector pipeline, and the validator to read from both the current candidates and the observation log.

### Minimal Implementation

**File: `collector.py`** — Write to observation log when generating candidates:

```python
def _append_observation_log(memory_id, candidate, loop_id):
    """Append an observation to the observation log."""
    log = load_observation_log()
    if "observations" not in log:
        log["observations"] = []
    
    log["observations"].append({
        "memory_id": memory_id,
        "source_loop": loop_id,
        "source_execution": candidate.get("source_execution", ""),
        "session_id": candidate.get("evidence", {}).get("session_id", ""),
        "output_hash": candidate.get("evidence", {}).get("output_hash", ""),
        "quality_score": candidate.get("quality_score", 0),
        "candidate_type": candidate.get("candidate_type", ""),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "origin": "runtime",
    })
    
    save_observation_log(log)
```

**File: `validator.py`** — Read observation log for cross-run evidence:

```python
def validate_candidates(candidates, quiet=False):
    # ... existing grouping logic ...
    
    # Phase 8.3: Cross-loop observation aggregation
    obs_log = load_observation_log()
    obs_by_memory = defaultdict(list)
    for obs in obs_log.get("observations", []):
        obs_by_memory[obs["memory_id"]].append(obs)
    
    for memory_id, group in groups.items():
        # Merge current candidates with observation log
        cross_loop_observations = obs_by_memory.get(memory_id, [])
        total_observations = len(group["executions"]) + len(cross_loop_observations)
        
        # Use total_observations for M4 gate
        validation_runs = total_observations
        # ... rest of validation logic ...
```

**File: `loop_controller.py`** — Pass `loop_id` to collector:

```python
# In Stage 6 (Collector):
candidates = collect_from_trace_ids([execution_id], quiet=True, update_state=False, loop_id=loop_id)
```

### Frozen Surfaces

- `collector.py` interface — `loop_id` parameter is optional, backward compatible
- `validator.py` — internal logic change, interface unchanged
- `memory-candidates.yaml` — unchanged format
- `validation-results.yaml` — unchanged format (adds `cross_loop_observations` field, additive)

### Tests Required

- `test_observation_log_populated`: Collector writes to observation log
- `test_cross_loop_aggregation`: Run 1 observation + Run 2 observation → validation_count >= 2
- `test_observation_log_idempotent`: Same execution not added twice
- `test_hypothesis_graduates`: Hypothesis with 1 obs → hypothesis. With 2 obs → validated

---

## 5. Promotion Evidence

### Root Cause

The promotion pipeline shows `promoted_this_cycle: 0` and `validated_ids: []` in most loop states. The promoter skips memories because of idempotency checks (`"already processed"`). But the real issue is that there's no evidence chain from runtime observation to promotion.

The current promotion flow:
```
candidates.yaml → validator → validation-results.yaml → promoter → promotion-results.yaml
```

The promoter reads `validation-results.yaml` and checks if the memory has already been processed. If yes, it skips. This is correct for idempotency. But the problem is that `validation-results.yaml` is overwritten each cycle, so the promoter never sees accumulated evidence.

### Architecture Impact

**Low.** The fix is to make the promoter read from the observation log (which accumulates cross-run) rather than relying solely on the current cycle's validation results.

### Minimal Implementation

**File: `promoter.py`** — Add observation-log-driven promotion:

```python
def promote_validated(validation_result, loop_id=None):
    # ... existing idempotency check ...
    
    # Phase 8.3: Cross-loop evidence chain
    memory_id = validation_result["memory_id"]
    obs_log = load_observation_log()
    obs_for_memory = [o for o in obs_log.get("observations", []) 
                      if o["memory_id"] == memory_id]
    
    # Record promotion provenance
    provenance = {
        "loop_id": loop_id,
        "observation_count": len(obs_for_memory),
        "observation_sources": [o["source_loop"] for o in obs_for_memory],
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # ... existing promotion logic, with provenance attached ...
```

**File: `promotion-results.yaml`** — Add provenance to each promoted entry:

```yaml
- memory_id: T-005
  status: applied
  provenance:
    loop_id: LOOP-20260903000001
    observation_count: 2
    observation_sources: [LOOP-20260902000001, LOOP-20260903000001]
    evidence_chain: [CAND-xxx, CAND-yyy]
```

### Frozen Surfaces

- `promoter.py` interface — `loop_id` parameter is optional, backward compatible
- `promotion-results.yaml` — adds `provenance` field, additive

### Tests Required

- `test_promotion_provenance`: Promoted memory has provenance with observation sources
- `test_promotion_evidence_chain`: validated_ids → promoted_ids with complete chain
- `test_promotion_idempotency_preserved`: Same memory not promoted twice

---

## 6. Implementation Order

The fixes are interdependent. The implementation order must be:

```
1. Artifact Authority (loop_id through all artifacts)
   ↓
2. Hypothesis Retrieval Priority (two-pass retrieval)
   ↓
3. Cross-loop Memory Lineage (test only — depends on #1 and #2)
   ↓
4. Validation Aggregation (observation log population)
   ↓
5. Promotion Evidence (provenance chain — depends on #4)
```

**Step 1 must come first** because all other steps need `loop_id` for lineage tracking.

---

## 7. Frozen Surfaces — Complete Inventory

| Surface | Modified? | How |
|---|---|---|
| Memory schema (`retrieval-index.yaml`) | **No** | No field changes |
| Memory content (`memory/*/*.md`) | **No** | Never modified |
| Benchmark tasks | **No** | No task changes |
| Scoring rubric | **No** | No scoring changes |
| Agent Prompt content | **No** | `[UNVALIDATED]` section unchanged |
| `retrieval_optimizer.retrieve()` interface | **No** | Internal two-pass logic, same return shape |
| `retrieval_adapter.adapt()` interface | **No** | Adds optional `loop_id` parameter, default None |
| `aos_host_adapter.get_context()` interface | **No** | Unchanged |
| `runtime_adapter` influence detection | **No** | Unchanged |
| `collector.collect_from_trace_ids()` interface | **No** | Adds optional `loop_id` parameter |
| `validator.validate_candidates()` interface | **No** | Internal logic change, same signature |
| `promoter.promote_validated()` interface | **No** | Adds optional `loop_id` parameter |
| Trace format | **No** | Unchanged |
| `promotion-policy.yaml` | **No** | Unchanged |
| `rejection-policy.yaml` | **No** | Unchanged |

---

## 8. Tests Required — Complete Inventory

| # | Test | File | Scenario |
|---|---|---|---|
| 1 | Artifact authority | `test_artifact_authority.py` | All artifacts from same loop share loop_id |
| 2 | Artifact lineage | `test_artifact_lineage.py` | loop_id consistent across artifacts |
| 3 | Cross-loop retrieval A | `test_cross_loop_lineage.py` | Run1 hypothesis → Run2 retrievable |
| 4 | Cross-loop retrieval B | `test_cross_loop_lineage.py` | Same task twice → same hypothesis |
| 5 | Cross-loop retrieval C | `test_cross_loop_lineage.py` | Different task → hypothesis NOT retrieved |
| 6 | Hypothesis lane | `test_hypothesis_retrieval_priority.py` | High-relevance hypothesis appears in lane |
| 7 | Established lane unchanged | `test_hypothesis_retrieval_priority.py` | Established memory ranking unchanged |
| 8 | Trust boundary | `test_hypothesis_retrieval_priority.py` | Hypothesis still has is_hypothesis + warning |
| 9 | Observation log populated | `test_observation_aggregation.py` | Collector writes to observation log |
| 10 | Cross-loop aggregation | `test_observation_aggregation.py` | Run1 + Run2 → validation_count >= 2 |
| 11 | Observation idempotency | `test_observation_aggregation.py` | Same execution not added twice |
| 12 | Hypothesis graduation | `test_observation_aggregation.py` | 1 obs → hypothesis, 2 obs → validated |
| 13 | Promotion provenance | `test_promotion_evidence.py` | Promoted memory has provenance |
| 14 | Promotion evidence chain | `test_promotion_evidence.py` | validated_ids → promoted_ids |
| 15 | Promotion idempotency | `test_promotion_evidence.py` | Same memory not promoted twice |

**Total: 15 tests.** All deterministic. No external runtime required.

---

## 9. Runtime Validation Plan

After implementation, verify the closed loop with a 2-run sequence:

### Run 1
```
Task: "Assess Redis cache TTL staleness for dashboard aggregates"
Expected:
  - Retrieval: established memories + task-relevant hypotheses
  - Agent: confirms hypotheses about cache patterns
  - Trace: hypothesis_confirmed influence
  - Collector: generates candidates for the hypotheses
  - Observation log: 1 new entry per hypothesis
  - Validator: hypothesis status (1 observation)
  - Loop state: validated_ids = [], hypothesis_ids = [H-xxx]
```

### Run 2
```
Task: "Same/similar Redis cache TTL task"
Expected:
  - Retrieval: Run 1 hypotheses appear in hypothesis_results lane
  - Agent: references the same hypotheses
  - Collector: generates candidates for the same hypotheses
  - Observation log: +1 entry per hypothesis → observation_count = 2
  - Validator: validated status (>= 2 observations)
  - Promoter: promoted_ids = [H-xxx]
  - Loop state: validated_ids = [H-xxx], promoted_ids = [H-xxx]
  - Artifact lineage: loop_id → retrieval_history → candidates → validation → promotion
```

### Success Criteria

```
Run 1 Memory → Run 2 Retrieval → Agent Influence → Validation Aggregation → Promotion
                                                                    ↑
                                                            All artifacts linked by loop_id
```

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Two-pass retrieval breaks existing ranking | Low | Medium | Established lane is unchanged. Hypothesis lane is additive. All existing tests pass. |
| Observation log grows unbounded | Low | Low | Log is per-memory_id. Cap at 10 entries per memory. |
| Idempotency breaks with new loop_id | Low | Low | Promoter uses memory_id + observation_count for idempotency, not loop_id. |
| Test modifies real index | Medium | High | Tests use `tempfile`/`copy` of index. Never modify the real index. |

---

## 11. Recommendation

**Proceed with implementation.** The 5 fixes are:

1. **Artifact Authority** — 4 files, ~20 lines changed. Adds `loop_id` to all artifacts.
2. **Cross-loop Memory Lineage** — 1 new test file, ~60 lines. Verifies Run1→Run2 retrieval.
3. **Hypothesis Retrieval Priority** — 1 file, ~30 lines changed. Two-pass retrieval with separate hypothesis lane.
4. **Validation Aggregation** — 2 files, ~40 lines changed. Population of observation log + cross-run reading.
5. **Promotion Evidence** — 1 file, ~20 lines changed. Provenance tracking in promotion results.

**Total: ~170 lines of code changes, 15 new tests.** No new features. No frozen surface violations. No benchmark changes.

The system after hardening will demonstrate a verifiable closed loop: `Run 1 → Memory → Run 2 → Retrieval → Influence → Validation → Promotion`. All artifacts traceable by `loop_id`. All evidence chainable.