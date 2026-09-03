# Phase 8.7 Implementation Plan — Adversarial Memory Integrity

**Date:** 2025-09-03
**Version:** v1
**Status:** READY FOR OPENCODE EXECUTION
**Basis:** `Phase-8.7-Architecture-Review.md` (APPROVED FOR IMPLEMENTATION)
**Constraint:** No code changes to frozen surfaces (promoter.py, retrieval_optimizer.py, retrieval_adapter.py, prompts/, benchmark templates)

---

## 1. Implementation Scope Map

| # | File | Function | Change | Invariant | Risk |
|---|------|----------|--------|-----------|------|
| 1 | `runtime_adapter.py` | `_determine_influence` | Add `observation_id`, `root_task_id`, `model_family`, `retrieval_context_hash` to `influence_breakdown[hid]` | I10, I13, I11 | LOW — additive fields, existing keys preserved |
| 2 | `runtime_adapter.py` | `build_trace` | Add `root_task_id` to trace top-level; add `model_family` derivation from `model` field | I10, I11 | LOW — additive, backward-compat defaults |
| 3 | `collector.py` | `generate_candidates` | Propagate `observation_id`, `root_task_id`, `model_family`, `retrieval_context_hash` from `influence_breakdown` into R7 hypothesis candidate dict | I10, I11, I13 | LOW — additive fields in candidate dict |
| 4 | `collector.py` | `generate_candidates` | Add `env_fingerprint` to candidate evidence block | I16 | LOW — additive |
| 5 | `collector.py` | `append_observation_log` | Add `observation_id`, `root_task_id`, `root_execution_id`, `model_family`, `retrieval_context_hash`, `env_fingerprint`, `countable` to observation log entry | I10, I11, I12, I13, I16 | LOW — additive fields |
| 6 | `collector.py` | `collect_from_trace_ids` | **REMOVE** `is_countable_observation` gate before `append_observation_log` — write ALL observations (including non-countable) with `countable: false` flag | I12 | **MEDIUM** — changes log write behavior; must preserve I7/I9 counting logic (only log write, not counting) |
| 7 | `collector.py` | `collect_from_trace_ids` | Add `root_task_id` propagation from trace to candidate (for candidates generated before R7) | I10 | LOW — additive |
| 8 | `collector.py` | `canonical_source_for` | No change — remains as-is for backward compat | — | — |
| 9 | `validator.py` | `group_candidates_by_memory` | After `canonical_source_for` dedup, apply second-level dedup: collapse same `root_task_id` and same `(model_family, retrieval_context_hash)` to one source | I10, I11 | **MEDIUM** — changes counting logic for hypothesis lane; must be guard-railed with `is_hyp` check |
| 10 | `validator.py` | `_build_result` | Add `counter_evidence_ratio`, `negative_evidence_count`, `env_fingerprint` to result dict | I12, I16 | LOW — additive |
| 11 | `validator.py` | `_build_result` | Add `staleness_warning` when `env_fingerprint` differs from previous observation | I16 | LOW — additive |
| 12 | `validator.py` | `_build_result` | Cap `confidence` for hypothesis lane: `min(validation_runs, 2) / MAX_OBSERVATIONS_FOR_FULL_CONFIDENCE` | I14 | LOW — hypothesis lane only, existing behavior for established lane |
| 13 | `validator.py` | `validate_memory_group` | After counting, compute `negative_evidence_count` from all candidates (including rejected) and `counter_evidence_ratio` | I12 | LOW — additive computation |
| 14 | `validator.py` | `enrich_groups_with_observation_log` | Add I10/I11 dedup to log-enriched groups; read `countable` flag instead of filtering by `same_loop_as_creation` | I10, I11, I12 | LOW — cleaner gate using explicit `countable` flag |
| 15 | `validator.py` | `synthesize_groups_from_observation_log` | Same I10/I11 dedup as above | I10, I11 | LOW |
| 16 | `runtime_adapter.py` | `build_trace` | Add `retrieval_diversity` audit metadata to trace (injection rank, injection frequency, rolling window diversity score) | I15 | LOW — audit-only |
| 17 | `tests/test_phase_8_7_integrity.py` | All new tests | 8-10 new tests covering I10-I16 | I10-I16 | LOW — additive, no regression risk |

### Frozen Surfaces Confirmed Untouched

| Surface | Check |
|---------|-------|
| `promotion/promoter.py` | NOT modified — receives same `validation-results.yaml` schema with extended fields |
| `retrieval/retrieval_optimizer.py` | NOT modified — `compute_adaptive_score` unchanged |
| `loop-controller/retrieval_adapter.py` | NOT modified — `adapt()` unchanged |
| `prompts/` | NOT modified |
| `benchmark templates` | NOT modified |

---

## 2. Data Schema Change Plan

### 2.1 New Fields in `influence_breakdown[hid]` (runtime_adapter.py)

| Field | Type | Source | Lifecycle | Default | Backward Compat |
|-------|------|--------|-----------|---------|-----------------|
| `observation_id` | `str` | Computed: `OBS-{execution_id}-{hypothesis_id}` | Created in `_determine_influence`, propagated through candidate → observation log → validation result | Generated on every call | YES — new field, old code ignores it |
| `root_task_id` | `str` | `trace["task_id"]` — the task that triggered this execution | Created in `build_trace`, stamped on candidate | `""` | YES — empty string when missing |
| `model_family` | `str` | Derived from `trace["model"]` by stripping version suffix (e.g., `claude-sonnet-4` → `claude-sonnet`) | Created in `build_trace` | `"unknown"` | YES — default when model field missing |
| `retrieval_context_hash` | `str` | `hashlib.sha256(json.dumps(sorted(hypotheses_injected)))` | Created in `_determine_influence` | `""` | YES — empty when no hypotheses injected |

### 2.2 New Fields in Trace Top-Level (runtime_adapter.py)

| Field | Type | Source | Default |
|-------|------|--------|---------|
| `root_task_id` | `str` | Same as `task_id` (the task that triggered this execution) | `""` |
| `model_family` | `str` | Derived from `model` | `"unknown"` |

### 2.3 New Fields in Candidate Dict (collector.py)

| Field | Type | Source | Default |
|-------|------|--------|---------|
| `observation_id` | `str` | Propagated from `influence_breakdown[hid]["observation_id"]` | `""` |
| `root_task_id` | `str` | Propagated from `influence_breakdown[hid]["root_task_id"]` or `trace["root_task_id"]` | `""` |
| `root_execution_id` | `str` | `trace["execution_id"]` | `""` |
| `model_family` | `str` | Propagated from `influence_breakdown[hid]["model_family"]` or `trace["model_family"]` | `"unknown"` |
| `retrieval_context_hash` | `str` | Propagated from `influence_breakdown[hid]["retrieval_context_hash"]` | `""` |
| `env_fingerprint` | `dict` | `{"python_version": sys.version, "code_version_hash": "...", "model_family": "..."}` | `{}` |
| `countable` | `bool` | Result of `is_countable_observation(candidate)` | `true` |

### 2.4 New Fields in Observation Log Entry (collector.py)

| Field | Type | Source | Default |
|-------|------|--------|---------|
| `observation_id` | `str` | Candidate `observation_id` | `""` |
| `root_task_id` | `str` | Candidate `root_task_id` | `""` |
| `root_execution_id` | `str` | Candidate `root_execution_id` | `""` |
| `model_family` | `str` | Candidate `model_family` | `"unknown"` |
| `retrieval_context_hash` | `str` | Candidate `retrieval_context_hash` | `""` |
| `env_fingerprint` | `dict` | Candidate `env_fingerprint` | `{}` |
| `countable` | `bool` | Candidate `countable` (pre-computed) | `true` |

### 2.5 New Fields in Validation Result (validator.py)

| Field | Type | Source | Default |
|-------|------|--------|---------|
| `negative_evidence_count` | `int` | Count of non-countable candidates in group | `0` |
| `counter_evidence_ratio` | `float` | `validation_runs / (validation_runs + negative_evidence_count)` | `1.0` |
| `env_fingerprint` | `dict` | From first countable observation | `{}` |
| `staleness_warning` | `bool` | `true` if env_fingerprint differs from previous observation | `false` |
| `staleness_detail` | `str` | Human-readable description of what changed | `""` |
| `evidence_independence` | `dict` | `{"root_task_ids": [...], "model_families": [...], "context_hashes": [...]}` | `{}` |
| `diversity_audit` | `dict` | `{"injection_rank": N, "window_frequency": N, "diversity_score": N}` | `{}` |

### 2.6 Backward Compatibility Guarantees

- All new fields default to safe values (`""`, `0`, `false`, `{}`, `[]`)
- Existing code that reads `influence_breakdown`, candidates, observation log, or validation results will ignore unknown keys (YAML/dict behavior)
- The `is_countable_observation` gate remains in `validator.py` counting logic — only the log write is changed to include non-countable entries
- Observation log entries without `countable` field are treated as `countable: true` (backward compat for old logs)
- Old observation logs without new fields work correctly: `root_task_id` defaults to `""`, `model_family` defaults to `"unknown"`, `retrieval_context_hash` defaults to `""`

---

## 3. Execution Order

### Step 1: runtime_adapter provenance extension

**File:** `runtime/loop-controller/runtime_adapter.py`

**Functions modified:**
- `_determine_influence` — add `observation_id`, `retrieval_context_hash` to `influence_breakdown[hid]`
- `build_trace` — add `root_task_id`, `model_family`, `env_fingerprint` to trace; add `retrieval_diversity` audit block

**Why first:**
- All downstream components (collector, validator) consume data from `runtime_adapter`
- These changes are purely additive — new fields in existing dicts
- Phase 8.6 behavior is 100% preserved: `same_loop_as_creation`, `created_loop`, `loop_id`, `source_loop` all unchanged
- If this step fails, no downstream step can be tested

**Risk:** LOW — additive fields in existing data structures

### Step 2: collector propagation

**File:** `runtime/memory-feedback/collector/collector.py`

**Functions modified:**
- `generate_candidates` — propagate new fields from `influence_breakdown` into R7 hypothesis candidates; add `env_fingerprint` to evidence block
- `append_observation_log` — write ALL candidates (not just countable) to observation log; add `countable` flag and all new provenance fields
- `collect_from_trace_ids` — remove `is_countable_observation` gate before `append_observation_log`; propagate `root_task_id` from trace to all candidates

**Why second:**
- Collector is the bridge between runtime_adapter traces and validator
- Must propagate new fields before validator can enforce invariants
- The key change (writing non-countable observations) is additive — old counting logic still works because `is_countable_observation` gate remains in validator

**Risk:** **MEDIUM** — the `is_countable_observation` gate removal for log writing is the most impactful change. Mitigation: the gate remains in validator counting logic. The log write change is isolated to `append_observation_log` caller.

### Step 3: validator enforcement

**File:** `runtime/memory-feedback/promotion/validator.py`

**Functions modified:**
- `group_candidates_by_memory` — add I10/I11 dedup after `canonical_source_for`
- `validate_memory_group` — compute `negative_evidence_count`, `counter_evidence_ratio`
- `_build_result` — add new fields to result; cap confidence for hypothesis lane; add `staleness_warning`
- `enrich_groups_with_observation_log` — read `countable` flag; apply I10/I11 dedup on log-derived observations
- `synthesize_groups_from_observation_log` — same I10/I11 dedup

**Why third:**
- Validator consumes data from collector, so collector must be updated first
- All new logic is guard-railed: `is_hypothesis` check before I10/I11 dedup, `hypothesis lane only` for confidence cap
- Phase 8.6 counting model (C1-C5) is preserved — I10/I11 are additional dedup dimensions, not replacements

**Risk:** **MEDIUM** — I10/I11 dedup changes counting for hypothesis lane. Mitigation: guard-railed with `is_hypothesis` check; established lane (R1-R6) unaffected.

### Step 4: tests

**File:** `runtime/loop-controller/tests/test_phase_8_7_integrity.py`

**Order:**
1. Write new tests using the frozen pipeline (`build_trace → collect_from_trace_ids → validate_candidates`)
2. Run new tests in isolation: `pytest tests/test_phase_8_7_integrity.py -v`
3. Fix any failures in new tests
4. Proceed to regression

**Risk:** LOW — new tests are additive

### Step 5: regression

**Command:**
```bash
pytest tests/test_phase_8_6_hypothesis_safety.py tests/test_phase_8_4_hypothesis_reinforcement.py tests/test_phase_8_5_integration.py -q
```

**Expected:** 56/56 PASS (20 + 27 + 9)

**If regression fails:**
- Check that `is_countable_observation` gate is still used in validator `group_candidates_by_memory` (lines 94-103)
- Check that `canonical_source_for` is still called before new I10/I11 dedup
- Check that established lane (R1-R6) is not affected by I10/I11 dedup (must be guard-railed with `is_hypothesis`)

### Why this order does not break Phase 8.6

1. **Step 1 is additive** — new fields in `influence_breakdown` and trace; existing keys unchanged
2. **Step 2 writes more data but validates the same** — collector writes non-countable observations to log but validator still uses `is_countable_observation` gate for counting
3. **Step 3 applies additional dedup, not replacement** — I10/I11 dedup runs AFTER `canonical_source_for` (C4), and only for hypothesis lane. C1-C5 logic is preserved.
4. **All new fields default safely** — empty strings, zeros, empty dicts
5. **56 existing tests exercise the frozen pipeline** — any regression is caught immediately

---

## 4. Test Strategy

### 4.1 Test File Structure

```
runtime/loop-controller/tests/test_phase_8_7_integrity.py
```

### 4.2 Test Cases (10 tests)

| Test | Invariant | Description | Expected Behavior |
|------|-----------|-------------|-------------------|
| `test_i10_same_root_task_fan_out_rejected` | I10 | Two hypothesis observations from same `root_task_id` but different `source_loop` | Counted as 1 distinct source, not 2 |
| `test_i10_different_root_task_independent` | I10 | Two hypothesis observations from different `root_task_id` | Counted as 2 distinct sources |
| `test_i11_same_model_same_context_collapsed` | I11 | Two observations with same `model_family` AND same `retrieval_context_hash` | Counted as 1 distinct source |
| `test_i11_different_model_independent` | I11 | Two observations with different `model_family` but same context | Counted as 2 distinct sources |
| `test_i12_negative_evidence_preserved` | I12 | One `reinforce_hypothesis` (countable) + one `weaken_hypothesis` (non-countable) | Observation log has 2 entries; `countable` field correct; `counter_evidence_ratio = 0.5` |
| `test_i12_inconclusive_preserved` | I12 | `inconclusive` observation | Logged with `countable: false`; validator reports in `negative_evidence_count` |
| `test_i13_observation_id_consistency` | I13 | Single hypothesis through pipeline | Same `observation_id` in `influence_breakdown`, candidate, observation log, validation result |
| `test_i14_confidence_capped` | I14 | Hypothesis with 5 distinct sources | `confidence = min(5, 2) / 5 = 0.4`, not `1.0` |
| `test_i14_established_confidence_uncapped` | I14 | Established memory with 5 sources | `confidence = 5/5 = 1.0` (unchanged) |
| `test_i16_env_fingerprint_audit` | I16 | Observation with `env_fingerprint` | `staleness_warning` computed correctly |

### 4.3 Test Patterns

Tests follow the same pattern as Phase 8.6 tests:

```python
# 1. Build traces with build_trace()
trace = build_trace(execution_id, trace_id, task_id, task_text, decision_context,
                    provider, model, runtime_result, loop_id=loop_id)

# 2. Write traces to temp dir
with tempfile.TemporaryDirectory() as tmpdir:
    # Write trace YAML files
    # Patch TRACES_DIR, OBSERVATION_LOG_FILE, etc.

    # 3. Collect candidates
    candidates = collect_from_trace_ids(trace_ids, quiet=True)

    # 4. Validate
    results = validator.validate_candidates(candidates, quiet=True)

    # 5. Assert
    assert result["validation_runs"] == expected_count
    assert result["counter_evidence_ratio"] == expected_ratio
```

### 4.4 Regression Baseline

```bash
pytest tests/test_phase_8_6_hypothesis_safety.py tests/test_phase_8_4_hypothesis_reinforcement.py tests/test_phase_8_5_integration.py -q
# Expected: 56 passed
```

---

## 5. Risk Review

### 5.1 Backward Compatibility

| Risk | Analysis | Mitigation |
|------|----------|------------|
| Old observation log entries lack new fields | Old entries have `countable` unset → treated as `true`; `root_task_id` empty → dedup falls back to `source_loop` (C4 behavior) | All new fields default to backward-compatible values |
| Old traces lack `model_family` | `build_trace` computes from `model` field; if missing, defaults to `"unknown"` | Default is safe — two `"unknown"` model families will be deduped by I11, which is conservative (fewer false positives) |
| `_build_result` schema change | Promoter reads `validation-results.yaml`; new fields are additive | YAML dicts tolerate unknown keys; promoter ignores new fields |
| I14 confidence cap affects promoter Trust Gate | `M4_confidence` uses `validation_runs` directly, not the capped `confidence` field | `M4_confidence` logic unchanged — `validation_runs` is still the raw count |

### 5.2 Schema Migration

- **No migration needed.** Old observation log entries are read as-is with defaults applied.
- Old log entries without `countable` are treated as `countable: true` (preserving existing behavior).
- Old log entries without `root_task_id` will have `""` and I10 dedup will not apply to them (both `""` → not deduped because they're not "same" — they're "unknown").
- New log entries are written with all fields populated.

### 5.3 Old Observation Logs

- Existing `memory-observation-log.yaml` entries are read with defaults (see §2.6)
- No schema migration script needed
- The `prune_observation_log` function (8.5-T3) is unchanged — it sorts by `observed_at` and keeps last N

### 5.4 Missing Metadata

| Scenario | Behavior |
|----------|----------|
| Trace has no `model` field | `model_family = "unknown"` |
| Trace has no `hypotheses_injected` | `retrieval_context_hash = ""` |
| Candidate has no `hypothesis_engagement` | I10/I11 dedup skipped (falls back to C4 `canonical_source_for`) |
| Candidate has no `env_fingerprint` | `staleness_warning = false` |
| `observation_id` missing | Empty string — no cross-component tracing possible |

### 5.5 Partial Pipeline Failure

| Failure | Impact | Recovery |
|---------|--------|----------|
| `runtime_adapter` fails to compute `observation_id` | Observation log has `observation_id = ""` | Non-critical — I13 is audit-only parity |
| `collector` fails to write observation log | Candidates still generated; validation still works without log enrichment | Observation log write is wrapped in `try/except` (existing pattern) |
| `validator` I10/I11 dedup produces unexpected count | Hypothesis may be under-counted or over-counted | Guard-railed with `is_hypothesis` check; established lane unaffected |
| `validator` `counter_evidence_ratio` is `1.0` (no negative evidence) | Correct for all-positive scenarios | Not an error — ratio `1.0` means all evidence is positive |

---

## 6. OpenCode Execution Brief

### Task: Phase 8.7 Adversarial Memory Integrity Implementation

**Execute in this exact order:**

#### Step 1: runtime_adapter.py — Add provenance metadata

Edit `/home/shade/.agents/runtime/loop-controller/runtime_adapter.py`:

1. In `_determine_influence`, add to `influence_breakdown[hid]`:
   - `observation_id = f"OBS-{execution_id}-{hid}"` (or use the `_loop_id` parameter)
   - `retrieval_context_hash = hashlib.sha256(json.dumps(sorted([h.get('memory_id','') for h in hyp_list]))).hexdigest()[:16]` if `hyp_list` else `""`
   - `root_task_id = task_id` (pass `task_id` as parameter)

2. In `build_trace`, add to trace dict:
   - `root_task_id = task_id`
   - `model_family = _extract_model_family(model)` where `_extract_model_family` strips the version suffix (e.g., `claude-sonnet-4-20250514` → `claude-sonnet-4`)
   - `env_fingerprint = { "python_version": sys.version.split()[0], "collector_version": "8.7" }`
   - `retrieval_diversity = { "hypotheses_injected_count": len(hyp_list), "audit_only": true }`

3. Add a helper function `_extract_model_family(model)` that parses model string into family name.

#### Step 2: collector.py — Propagate fields and write all observations

Edit `/home/shade/.agents/runtime/memory-feedback/collector/collector.py`:

1. In `generate_candidates`, for R7 hypothesis candidates:
   - Propagate `observation_id`, `root_task_id`, `model_family`, `retrieval_context_hash` from `influence_breakdown[hid]`
   - Add `root_execution_id = trace["execution_id"]`
   - Add `env_fingerprint = trace.get("env_fingerprint", {})` to evidence block
   - Add `countable = is_countable_observation(candidate)` (pre-compute)

2. In `collect_from_trace_ids`:
   - **DELETE** the `is_countable_observation` gate before `append_observation_log` (lines 541-543)
   - **REPLACE** with: call `append_observation_log` for ALL candidates, regardless of `is_countable_observation`
   - Propagate `root_task_id` from `trace.get("root_task_id", trace.get("task_id", ""))` to all candidates

3. In `append_observation_log`:
   - Add all new fields (`observation_id`, `root_task_id`, `root_execution_id`, `model_family`, `retrieval_context_hash`, `env_fingerprint`, `countable`)
   - Read from `candidate` dict with safe defaults

#### Step 3: validator.py — Enforce I10-I14, audit I15-I16

Edit `/home/shade/.agents/runtime/memory-feedback/promotion/validator.py`:

1. In `group_candidates_by_memory`, after `canonical_source_for` dedup:
   - For hypothesis lane only (`is_hyp`):
     - Track `seen_root_task_ids = set()` and `seen_model_contexts = set()`
     - Before adding to `executions`, check: `root_task_id not in seen_root_task_ids` AND `(model_family, retrieval_context_hash) not in seen_model_contexts`
     - Only add to `executions` if both conditions pass
     - Add to `seen_*` sets after adding

2. In `validate_memory_group`:
   - Count `negative_evidence_count = len([c for c in group["candidates"] if not c.get("countable", True)])`
   - Compute `counter_evidence_ratio = validation_runs / max(validation_runs + negative_evidence_count, 1)`
   - Pass to `_build_result`

3. In `_build_result`:
   - For hypothesis lane (`is_hypothesis`), cap confidence: `min(validation_runs, 2) / MAX_OBSERVATIONS_FOR_FULL_CONFIDENCE`
   - Add `negative_evidence_count`, `counter_evidence_ratio`, `env_fingerprint`, `staleness_warning`, `staleness_detail`, `evidence_independence`
   - Compute `staleness_warning` by comparing `env_fingerprint` with previous observation (from observation log)

4. In `enrich_groups_with_observation_log` and `synthesize_groups_from_observation_log`:
   - Read `countable` flag from log entries instead of re-computing `is_countable_observation`
   - Apply same I10/I11 dedup to log-derived observations

#### Step 4: tests/test_phase_8_7_integrity.py — Write and verify

Create `/home/shade/.agents/runtime/loop-controller/tests/test_phase_8_7_integrity.py`:

- 10 tests as specified in §4.2
- Follow the same patterns as `test_phase_8_6_hypothesis_safety.py`
- Use the frozen pipeline: `build_trace() → collect_from_trace_ids() → validate_candidates()`

#### Step 5: Run regression

```bash
cd /home/shade/.agents/runtime/loop-controller
pytest tests/test_phase_8_6_hypothesis_safety.py tests/test_phase_8_4_hypothesis_reinforcement.py tests/test_phase_8_5_integration.py -q
# MUST BE: 56 passed
```

Then run new tests:
```bash
pytest tests/test_phase_8_7_integrity.py -v
# MUST BE: 10 passed
```

---

### Frozen Surface Constraint (DO NOT TOUCH)

| File | Status |
|------|--------|
| `promotion/promoter.py` | **FROZEN** |
| `retrieval/retrieval_optimizer.py` | **FROZEN** |
| `loop-controller/retrieval_adapter.py` | **FROZEN** |
| `prompts/` | **FROZEN** |
| `benchmark templates` | **FROZEN** |

### Allowed Files

| File | Allowed |
|------|---------|
| `runtime/loop-controller/runtime_adapter.py` | **YES** |
| `runtime/memory-feedback/collector/collector.py` | **YES** |
| `runtime/memory-feedback/promotion/validator.py` | **YES** |
| `runtime/loop-controller/tests/test_phase_8_7_integrity.py` | **YES (new file)** |

---

**Phase 8.7 Implementation Plan v1 — Ready for OpenCode execution.**