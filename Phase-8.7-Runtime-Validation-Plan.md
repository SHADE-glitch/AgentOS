# Phase 8.7 Runtime Validation Plan

**Date:** 2025-09-03
**Version:** v1
**Status:** READY FOR OPENCODE EXECUTION
**Basis:** Phase 8.7 Implementation (67/67 tests PASS, frozen surfaces clean)
**Constraint:** No code modification; no frozen surface mutation; validation artifacts only

---

## 1. Validation Objective

Phase 8.7 Runtime Validation must prove that the **adversarial memory integrity invariants (I10-I16)** hold at runtime — not merely that the code compiles or that unit tests pass, but that the pipeline produces correct artifacts when subjected to adversarial inputs.

### What must be proven

| # | Claim | Proof required |
|---|-------|---------------|
| C1 | **Memory identity is not contaminated** | observation_id is identical across all pipeline stages for the same observation |
| C2 | **Evidence independence is enforced** | Two observations from the same root_task_id produce only 1 distinct evidence source |
| C3 | **Multi-agent echo is detected** | Two observations with same model_family + same retrieval_context_hash produce only 1 distinct evidence source |
| C4 | **Negative evidence is not lost** | weaken/inconclusive observations appear in the observation log with countable=false |
| C5 | **Confidence is not amplified by exposure** | Hypothesis confidence is capped at 0.4 regardless of observation count |
| C6 | **Context drift is detectable** | Changes in env_fingerprint produce staleness_warning=true |

### What is NOT being validated

- Unit test correctness (already proven: 67/67 PASS)
- Frozen surface integrity (already verified)
- Promoter behavior (out of scope for Phase 8.7)
- Retrieval ranking (frozen surface)

---

## 2. Runtime Attack Scenarios

### Case 1 — Evidence Fan-Out Attack

**Scenario:**
A single root task ("TASK-ROOT") executes in two different loops (LOOP-A, LOOP-B). Each loop produces a `reinforce_hypothesis` candidate for the same hypothesis H-888. The two candidates have different `source_execution` values, different `loop_id` values, and would pass Phase 8.6 C4 `canonical_source` dedup. But they share the same `root_task_id`.

**Crafted Input:**
```
Trace 1:
  execution_id: EXEC-FO-1, loop_id: LOOP-FO-A, root_task_id: TASK-ROOT
  influence_breakdown[H-888]: reinforce_hypothesis, observed, same_loop=false

Trace 2:
  execution_id: EXEC-FO-2, loop_id: LOOP-FO-B, root_task_id: TASK-ROOT
  influence_breakdown[H-888]: reinforce_hypothesis, observed, same_loop=false
```

**Expected Artifact:**
In `validation-results.yaml` for H-888:
- `validation_runs: 1` (not 2)
- `evidence_independence.root_task_ids: ["TASK-ROOT"]` (only 1 distinct root)
- `evidence_sources: ["LOOP-FO-A"]` (only 1 distinct source)

**PASS criteria:**
`validation_runs == 1` for H-888 despite 2 traces with different loops.

---

### Case 2 — Multi-Agent Echo Attack

**Scenario:**
Two agents in different loops both confirm hypothesis H-888. Both agents use the same model family (`claude-sonnet`) and received the same set of hypotheses injected (`retrieval_context_hash` identical). The agents have different `source_execution` and different `root_task_id`, so I10 would count them as independent. But I11 must collapse them.

**Crafted Input:**
```
Trace 1:
  execution_id: EXEC-ECHO-1, root_task_id: TASK-ECHO-1
  model_family: claude-sonnet
  retrieval_context_hash: abc123def4567890
  influence_breakdown[H-888]: reinforce_hypothesis, observed

Trace 2:
  execution_id: EXEC-ECHO-2, root_task_id: TASK-ECHO-2
  model_family: claude-sonnet
  retrieval_context_hash: abc123def4567890
  influence_breakdown[H-888]: reinforce_hypothesis, observed
```

**Expected Artifact:**
In `validation-results.yaml` for H-888:
- `validation_runs: 1` (not 2)
- `evidence_independence.model_families: ["claude-sonnet"]` (only 1 distinct model)
- `evidence_independence.context_hashes: ["abc123def4567890"]` (only 1 distinct context)

**PASS criteria:**
`validation_runs == 1` for H-888 despite different root_task_ids.

---

### Case 3 — Negative Evidence Injection

**Scenario:**
Three observations of the same hypothesis H-888 are collected:
1. A `reinforce_hypothesis` with `observed` outcome (countable)
2. A `reinforce_hypothesis` with `inconclusive` outcome (non-countable)
3. A `weaken_hypothesis` (non-countable, rejected by validator)

**Crafted Input:**
```
Trace 1:
  execution_id: EXEC-NEG-1, loop_id: LOOP-NEG-A, root_task_id: TASK-NEG-1
  influence_breakdown[H-888]: reinforce_hypothesis, observed, term_matches=3, id_mentioned=true

Trace 2:
  execution_id: EXEC-NEG-2, loop_id: LOOP-NEG-B, root_task_id: TASK-NEG-2
  influence_breakdown[H-888]: reinforce_hypothesis, inconclusive, term_matches=1, id_mentioned=false

Trace 3:
  execution_id: EXEC-NEG-3, loop_id: LOOP-NEG-C, root_task_id: TASK-NEG-3
  influence_breakdown[H-888]: weaken_hypothesis, weaken
```

**Expected Artifacts:**
In `memory-observation-log.yaml`:
- 3 entries for H-888
- Entry 1: `countable: true`
- Entry 2: `countable: false`
- Entry 3: `countable: false`

In `validation-results.yaml` for H-888:
- `validation_runs: 1` (only the first countable observation)
- `negative_evidence_count: 2`
- `counter_evidence_ratio: 0.33` (1 / (1+2))

**PASS criteria:**
- Observation log has exactly 3 entries for H-888
- `countable` flags are correct
- `counter_evidence_ratio == 0.33`

---

### Case 4 — Observation Identity Trace

**Scenario:**
A single observation of hypothesis H-888 flows through the entire pipeline. The `observation_id` must be identical at every stage.

**Crafted Input:**
```
Trace 1:
  execution_id: EXEC-OID-1, loop_id: LOOP-OID-A, root_task_id: TASK-OID
  influence_breakdown[H-888]:
    observation_id: OBS-EXEC-OID-1-H-888
    reinforce_hypothesis, observed
```

**Expected Identity Chain:**
```
runtime_adapter: influence_breakdown["H-888"]["observation_id"] == "OBS-EXEC-OID-1-H-888"
  ↓
collector:       candidate["observation_id"] == "OBS-EXEC-OID-1-H-888"
  ↓
observation log: log_entry["observation_id"] == "OBS-EXEC-OID-1-H-888"
  ↓
validator:       result["observation_id"] == "OBS-EXEC-OID-1-H-888"
```

**PASS criteria:**
All 4 stages report the same `observation_id` value.

---

### Case 5 — Feedback Amplification

**Scenario:**
Hypothesis H-888 has been observed 5 times across 5 distinct loops, each with unique `root_task_id`, `model_family`, and `retrieval_context_hash`. In Phase 8.6, this would produce `confidence = 1.0` (5/5). But Phase 8.7 I14 caps hypothesis confidence at 2 observations.

**Crafted Input:**
```
5 traces, each with:
  - unique execution_id (EXEC-FB-1 through EXEC-FB-5)
  - unique loop_id (LOOP-FB-1 through LOOP-FB-5)
  - unique root_task_id (TASK-FB-1 through TASK-FB-5)
  - unique model_family (model-1 through model-5)
  - unique retrieval_context_hash (ctx-1 through ctx-5)
  - all influence_breakdown[H-888]: reinforce_hypothesis, observed, id_mentioned=true
```

**Expected Artifact:**
In `validation-results.yaml` for H-888:
- `validation_runs: 5` (all 5 counted as distinct)
- `confidence: 0.4` (capped at min(5,2)/5 = 0.4)
- `status: validated` (passes 2-source threshold)

**Contrast (established memory):**
An established memory "TASK-CTRL" with 5 reinforce observations:
- `confidence: 1.0` (uncapped)

**PASS criteria:**
- Hypothesis confidence == 0.4 (not 1.0)
- Established confidence == 1.0 (unchanged)
- Hypothesis still validated (status != rejected)

---

### Case 6 — Context Drift Detection

**Scenario:**
Two observations of hypothesis H-888 are collected under different environment fingerprints. The first was collected under Python 3.10 with model `claude-sonnet`. The second was collected under Python 3.11 with model `gpt-4`.

**Crafted Input:**
```
Trace 1:
  execution_id: EXEC-DRIFT-1, loop_id: LOOP-DRIFT-A, root_task_id: TASK-DRIFT-1
  env_fingerprint: {"python_version": "3.10.0", "collector_version": "8.7", "model_family": "claude-sonnet"}
  influence_breakdown[H-888]: reinforce_hypothesis, observed

Trace 2:
  execution_id: EXEC-DRIFT-2, loop_id: LOOP-DRIFT-B, root_task_id: TASK-DRIFT-2
  env_fingerprint: {"python_version": "3.11.0", "collector_version": "8.7", "model_family": "gpt-4"}
  influence_breakdown[H-888]: reinforce_hypothesis, observed
```

**Expected Artifact:**
In `validation-results.yaml` for H-888:
- `staleness_warning: true`
- `staleness_detail: "env_fingerprint changed across 2 observations"`
- `env_fingerprint: {"python_version": "3.10.0", ...}` (first observed)

**Contrast (same environment):**
Two observations with identical `env_fingerprint`:
- `staleness_warning: false`

**PASS criteria:**
- Mixed env: `staleness_warning == true`
- Same env: `staleness_warning == false`

---

## 3. Validation Matrix

| # | Attack | Input | Invariant | Expected Artifact | PASS Criteria |
|---|--------|-------|-----------|-------------------|---------------|
| 1 | Evidence Fan-Out | 2 traces, same `root_task_id`, different `loop_id` | I10 Evidence Independence | `validation-runs.yaml`: `validation_runs=1` | `validation_runs == 1`, `root_task_ids` count == 1 |
| 2 | Multi-Agent Echo | 2 traces, same `model_family` + same `retrieval_context_hash`, different `root_task_id` | I11 Causal Independence | `validation-runs.yaml`: `validation_runs=1` | `validation_runs == 1`, `model_families` count == 1 |
| 3 | Negative Evidence | 3 traces: observed + inconclusive + weaken | I12 Negative Evidence Preservation | `observation-log.yaml`: 3 entries; `validation-runs.yaml`: `negative_evidence_count=2`, `counter_evidence_ratio=0.33` | Log has 3 entries; `countable` flags correct; ratio == 0.33 |
| 4 | Observation Identity | 1 trace, check `observation_id` at 4 pipeline stages | I13 Single Observation Identity | Same `observation_id` in trace, candidate, log, result | All 4 stages report identical `observation_id` |
| 5 | Feedback Amplification | 5 traces, all distinct sources, hypothesis lane | I14 No Positive Feedback | `validation-runs.yaml`: `confidence=0.4` (capped) | Hypothesis confidence == 0.4; established confidence == 1.0 |
| 6 | Context Drift | 2 traces, different `env_fingerprint` | I16 Context-Bounded Validity | `validation-runs.yaml`: `staleness_warning=true` | `staleness_warning == true`; same-env control == false |

### Runtime Validation Coverage Summary

| Invariant | Tested via | Case |
|-----------|-----------|------|
| I10 Evidence Independence | Runtime Case 1 | Fan-Out Attack |
| I11 Causal Independence | Runtime Case 2 | Echo Attack |
| I12 Negative Evidence Preservation | Runtime Case 3 | Negative Injection |
| I13 Single Observation Identity | Runtime Case 4 | Identity Trace |
| I14 No Positive Feedback | Runtime Case 5 | Amplification |
| I15 Retrieval Diversity | Audit-only — verified via `retrieval_diversity` metadata in trace (not runtime validation) | N/A |
| I16 Context-Bounded Validity | Runtime Case 6 | Drift Detection |

---

## 4. Runtime Constraints

### 4.1 Mandatory Constraints

| Constraint | Detail |
|------------|--------|
| **No code modification** | Zero changes to any `.py` file. Validation is read-only consumption of the pipeline. |
| **No frozen surface mutation** | `promoter.py`, `retrieval_optimizer.py`, `retrieval_adapter.py`, `prompts/`, `benchmark templates` — untouched. |
| **No memory lifecycle change** | No promotion, no demotion, no state mutation. Validation produces audit artifacts only. |
| **Validation artifacts only** | Output is: `Phase-8.7-Runtime-Validation-Report.md` + trace YAML files in a temp directory. No permanent files written to runtime paths. |

### 4.2 Validation Environment

| Setting | Value |
|---------|-------|
| Working directory | Isolated temp directory (not `runtime/traces/`) |
| Observation log | Isolated temp file (not `memory-observation-log.yaml`) |
| Candidates file | Isolated temp file (not `memory-candidates.yaml`) |
| Validation results | Isolated temp file (not `validation-results.yaml`) |
| State file | Disabled (`update_state=False`) |

### 4.3 Pipeline Stages Used

Each case exercises the frozen pipeline:
```
build_trace() → write trace YAML → collect_from_trace_ids() → validate_candidates()
```

- `build_trace()` — from `runtime_adapter.py` (Phase 8.7 provenance fields must be present)
- `collect_from_trace_ids()` — from `collector.py` (I12 negative evidence must be logged)
- `validate_candidates()` — from `validator.py` (I10/I11 dedup, I14 confidence cap, I16 staleness)
- Observation log read — verify I12 and I13

---

## 5. OpenCode Execution Brief

### Task: Phase 8.7 Runtime Validation

**Execute 6 validation cases in isolated temp directories. Produce a validation report.**

### Setup

```bash
cd /home/shade/.agents/runtime/loop-controller
```

### Execution Order

#### Case 1: Evidence Fan-Out Attack (I10)

1. Build two traces with:
   - Same `execution_id` prefix: `EXEC-FO-1`, `EXEC-FO-2`
   - Same `root_task_id`: `TASK-ROOT`
   - Different `loop_id`: `LOOP-FO-A`, `LOOP-FO-B`
   - Hypothesis: `H-888-ADVERSARIAL`
   - Both `reinforce_hypothesis`, `observed`, `id_mentioned=true`, `changed_decision=true`

2. Write traces to temp dir. Run `collect_from_trace_ids` then `validate_candidates`.

3. Assert:
   ```python
   result = validation_results["H-888-ADVERSARIAL"]
   assert result["validation_runs"] == 1, f"Expected 1, got {result['validation_runs']}"
   assert len(result["evidence_independence"]["root_task_ids"]) == 1
   ```

#### Case 2: Multi-Agent Echo Attack (I11)

1. Build two traces with:
   - Different `execution_id`: `EXEC-ECHO-1`, `EXEC-ECHO-2`
   - Different `root_task_id`: `TASK-ECHO-1`, `TASK-ECHO-2`
   - **Same** `model_family`: `claude-sonnet`
   - **Same** `retrieval_context_hash`: compute from same `hypotheses_injected` list
   - Hypothesis: `H-888-ADVERSARIAL`

2. Collect and validate.

3. Assert:
   ```python
   result = validation_results["H-888-ADVERSARIAL"]
   assert result["validation_runs"] == 1, f"Expected 1, got {result['validation_runs']}"
   assert len(result["evidence_independence"]["model_families"]) == 1
   ```

#### Case 3: Negative Evidence Injection (I12)

1. Build three traces:
   - Trace 1: `reinforce_hypothesis`, `observed`, `id_mentioned=true`, `term_matches=3`
   - Trace 2: `reinforce_hypothesis`, `inconclusive`, `id_mentioned=false`, `term_matches=1`
   - Trace 3: `weaken_hypothesis`, `weaken`, `id_mentioned=true`

2. Collect and validate.

3. Assert:
   ```python
   # Observation log check
   log_entries = [o for o in observation_log if o["memory_id"] == "H-888-ADVERSARIAL"]
   assert len(log_entries) == 3, f"Expected 3 log entries, got {len(log_entries)}"
   countable_flags = {o["source_loop"]: o["countable"] for o in log_entries}
   assert sum(1 for v in countable_flags.values() if v) == 1  # exactly 1 countable
   assert sum(1 for v in countable_flags.values() if not v) == 2  # exactly 2 non-countable

   # Validation result check
   result = validation_results["H-888-ADVERSARIAL"]
   assert result["negative_evidence_count"] == 2
   assert result["counter_evidence_ratio"] == 0.33
   assert result["validation_runs"] == 1
   ```

#### Case 4: Observation Identity Trace (I13)

1. Build one trace with `execution_id=EXEC-OID-1`.

2. Check `observation_id` at each stage:
   ```python
   # Stage 1: trace
   obs_id_trace = trace["memory_retrieval"]["influence_breakdown"]["H-888-ADVERSARIAL"]["observation_id"]
   assert obs_id_trace == "OBS-EXEC-OID-1-H-888-ADVERSARIAL"

   # Stage 2: candidate
   cand = [c for c in candidates if c["target_memory"] == "H-888-ADVERSARIAL"][0]
   assert cand["observation_id"] == obs_id_trace

   # Stage 3: observation log
   log_entry = [o for o in observation_log if o["memory_id"] == "H-888-ADVERSARIAL"][0]
   assert log_entry["observation_id"] == obs_id_trace

   # Stage 4: validation result
   result = validation_results["H-888-ADVERSARIAL"]
   assert result["observation_id"] == obs_id_trace
   ```

#### Case 5: Feedback Amplification (I14)

1. Build 5 traces for hypothesis `H-888-ADVERSARIAL`, each with:
   - Unique `execution_id`, `loop_id`, `root_task_id`, `model_family`, `retrieval_context_hash`
   - All `reinforce_hypothesis`, `observed`, `id_mentioned=true`

2. Build 5 traces for established memory `TASK-CTRL-001`, each with:
   - Unique `execution_id`, `loop_id`
   - All `reinforce`, `observed`

3. Collect and validate both.

4. Assert:
   ```python
   hyp_result = validation_results["H-888-ADVERSARIAL"]
   est_result = validation_results["TASK-CTRL-001"]
   assert hyp_result["confidence"] == 0.4, f"Hypothesis confidence should be 0.4, got {hyp_result['confidence']}"
   assert est_result["confidence"] == 1.0, f"Established confidence should be 1.0, got {est_result['confidence']}"
   assert hyp_result["validation_runs"] == 5  # all counted, just confidence capped
   ```

#### Case 6: Context Drift (I16)

1. Build two traces with:
   - Trace 1: `env_fingerprint={"python_version": "3.10.0", "collector_version": "8.7", "model_family": "claude-sonnet"}`
   - Trace 2: `env_fingerprint={"python_version": "3.11.0", "collector_version": "8.7", "model_family": "gpt-4"}`
   - Different `root_task_id`, `model_family`, `retrieval_context_hash` (to pass I10/I11)

2. Build control: two traces with identical `env_fingerprint`.

3. Assert:
   ```python
   drift_result = validation_results["H-888-ADVERSARIAL"]
   assert drift_result["staleness_warning"] == True
   assert drift_result["staleness_detail"] != ""

   control_result = validation_results["H-999-CONTROL"]
   assert control_result["staleness_warning"] == False
   ```

### Final Report

Write `benchmark-8.7/Phase-8.7-Runtime-Validation-Report.md` containing:

1. **Summary**: PASS/FAIL for each of 6 cases
2. **Per-case details**: input description, expected output, actual output, verdict
3. **Artifact checksums**: observation log, validation results paths
4. **Regression check**: confirm 67/67 existing tests still PASS
5. **Frozen surface check**: confirm no modifications to frozen files

### Frozen Surface Verification (post-validation)

```bash
# Verify no frozen files were modified
git diff --name-only HEAD -- \
  runtime/memory-feedback/promotion/promoter.py \
  runtime/memory-feedback/retrieval/retrieval_optimizer.py \
  runtime/loop-controller/retrieval_adapter.py \
  prompts/
# Expected: no output (no changes)
```

---

**Phase 8.7 Runtime Validation Plan v1 — Ready for OpenCode execution.**