# Phase 8.8 Stress Validation Plan — Memory Integrity Long-Horizon & Adversarial Sequence

**Date:** 2025-09-03
**Version:** v1
**Status:** READY FOR OPENCODE EXECUTION
**Basis:** Phase 8.7 Complete (I10-I14/I16 PASS, 67/67 regression PASS, frozen surfaces clean)
**Constraint:** Validation artifacts only — no `.py` modification, no frozen surface mutation, no production memory mutation, isolated temp dirs, `update_state=False`

---

## 1. Validation Objectives

Phase 8.8 must prove that Phase 8.7 adversarial invariants **remain stable under scale, saturation, and ordered adversarial sequences** — not only for single or paired observations, but for long horizons where drift, duplication, and replay accumulate.

### 1.1 What Phase 8.7 already proved

| Invariant | Claim | Proven via |
|-----------|-------|------------|
| I10 Evidence Independence | Same `root_task_id` → 1 distinct source | Case 1 Fan-Out PASS |
| I11 Causal Independence | Same `(model_family, retrieval_context_hash)` → 1 distinct source | Case 2 Echo PASS |
| I12 Negative Evidence Preservation | `weaken`/`inconclusive` logged `countable=false`, `ratio` correct | Case 3 Negative PASS |
| I13 Observation Identity | `observation_id` identical across 4 stages | Case 4 Identity PASS |
| I14 Confidence Amplification Protection | Hypothesis `confidence` capped at `0.4` | Case 5 Amplification PASS |
| I16 Context Drift Detection | Different `env_fingerprint` → `staleness_warning=true` | Case 6 Drift PASS |
| Regression | 67/67 tests PASS | Pipeline |
| Frozen surfaces | `promoter.py`, `retrieval_optimizer.py`, `retrieval_adapter.py`, `prompts/` untouched | `git diff` |

### 1.2 What Phase 8.8 must prove

| # | Invariant | Claim | Proof required | Risk if unproven |
|---|-----------|-------|----------------|------------------|
| I17 | **Long Horizon Stability** | `confidence`, `validation_runs`, `evidence_independence` do not drift or degrade across 100/500/1000 mixed observations | At least 3 horizon checkpoints (100, 500, 1000) with mixed hypothesis + established memories; metrics flat within bounds | Confidence inflation or dedup leak over time → hyp graduates incorrectly after long exposure |
| I18 | **Memory Saturation** | With 1000 distinct hypotheses, grouping, I10/I11 dedup, and validator runtime remain correct and bounded | Generate 1000 distinct `H-xxx` each with 2 distinct observations (2000 traces); verify `len(groups)==1000`, each `validation_runs==2`, runtime < threshold | Hash collisions, `group_candidates_by_memory` pollution, O(n²) dedup, or log cap corruption at scale |
| I19 | **Adversarial Sequence Attack** | Ordered sequence `reinforce → reinforce → weaken → reinforce → echo(collapsed) → drift` preserves I12/I11/I14 correctly | Single `H-888` subjected to 6-step sequence; verify `negative_evidence_count`, echo collapsed, confidence bounded, drift flagged | Order-dependent counting (e.g., weaken after reinforce treated as reinforce), or echo/drift counted after weaken |
| I20 | **Replay Attack** | Replaying the identical observation N times produces no new distinct evidence | Same `observation_id`/`source_execution`/`root_task_id`/`model_family`/`retrieval_context_hash` replayed 5× and 10×; `validation_runs` unchanged, `confidence` unchanged, `observation_id` unchanged | Canonical source dedup leak allows replay to inflate `validation_runs` or clone `observation_id` |

### 1.3 What is NOT being validated

- Unit test correctness (already 67/67)
- Promoter lifecycle (out of scope; frozen)
- Retrieval ranking (frozen `retrieval_optimizer.py` / `retrieval_adapter.py`)
- Real provider latency or token cost

---

## 2. Invariant Definitions (I17-I20)

### I17 Long Horizon Stability

**Statement:** For a fixed `H-888` observed repeatedly with a stable mixture of countable and non-countable evidence, `validation_runs`, `confidence`, `negative_evidence_count`, `counter_evidence_ratio`, and `evidence_independence` sizes remain stable as horizon grows from 100 → 500 → 1000, modulo expected cap.

**Metrics tracked:**
- `validation_runs` = count of distinct `canonical_source` after I10/I11 dedup (not raw trace count)
- `confidence` = `min(min(runs,2)/5, 1.0)` for hypothesis (I14) — must stay `0.4` once `runs≥2`
- `evidence_independence.root_task_ids` size = distinct roots after dedup
- `negative_evidence_count` and `counter_evidence_ratio` = stable counters

**Stability criterion:** For horizons H=100,500,1000 generated with identical distribution (e.g., 80% countable `reinforce_hypothesis` observed, 10% `inconclusive`, 10% `weaken` with `same_loop=true`), `validation_runs` at 100, 500, 1000 must be **proportional to distinct sources, not raw count** and must not monotonically inflate due to horizon length. Confidence must remain `0.4` (not `1.0`) for all `H≥2`.

### I18 Memory Saturation

**Statement:** At 1000 distinct hypotheses, `group_candidates_by_memory` produces exactly 1000 groups, each respecting I10/I11 dedup and I14 cap, with wall-clock runtime bounded.

**Thresholds:**
- `len(groups) == 1000` (no loss, no merge)
- For each sampled group (at least 10 random), `validation_runs==2` when given 2 distinct sources with distinct `root_task_id`/`model_family`/`retrieval_context_hash`
- Group where same `root_task_id` repeated → `validation_runs==1`
- Validator total wall time for 2000 candidates (1000×2) < `2.0s` on CI (regression guard, not benchmark); primarily asserts no super-linear blowup vs 100-hyp baseline (e.g., < `5×` of 100-hyp time)

### I19 Adversarial Sequence Attack

**Statement:** The 6-step ordered attack on single `H-888` must be handled commutatively: final artifacts equal set Semantics, not sequence order, for I12/I11/I14/I16.

**Sequence (per `H-888`):**
1. `reinforce` `observed` (countable) — root `TASK-SEQ-1`, model `claude-sonnet`, ctx `ctx-1`
2. `reinforce` `observed` (countable) — root `TASK-SEQ-2`, model `gpt-4`, ctx `ctx-2` (distinct → `runs=2`)
3. `weaken` `refuted` with `same_loop=true` (non-countable via I9) — root `TASK-SEQ-3`, model `claude-sonnet`, ctx `ctx-3`
4. `reinforce` `observed` (countable) — root `TASK-SEQ-4`, model `model-4`, ctx `ctx-4` (distinct)
5. `echo` — repeat of step 2's `(root=TASK-SEQ-2, model=gpt-4, ctx=ctx-2)` but new `LOOP-ECHO`/`EXEC-ECHO` → must collapse via I11 (not new run)
6. `drift` — `reinforce` `observed` countable but `env_fingerprint={"python_version":"3.11.0", ...}` distinct from prior `3.10.0` → `staleness_warning=true`

**Final expectations** after all 6 steps (log 6 entries, 3 countable distinct sources from steps 1,2,4 plus echo collapsed, drift adds but must respect I10/I11):
- `validation_runs == 3` (steps 1,2,4 distinct; step3 non-countable; step5 collapsed; step6 is `TASK-SEQ-6` distinct? Actually step6 root distinct `TASK-SEQ-6`, model `drift-model`, ctx `ctx-6` distinct → would be 4, but plan defines echo+drift after 3 reinforces → choose to make step6 distinct root to test drift flag while counting. For deterministic plan, set step6 `root=TASK-SEQ-6` distinct → `runs=4`. Document both interpretations; PASS criterion below fixes one.
- Simplified deterministic PASS (chosen): steps 1,2,4,6 are 4 distinct countable sources → `runs==4`, `confidence==0.4` (capped), `negative==1` (step3), `counter==0.8` (4/5), echo not counted, `staleness_warning==true`.

To avoid ambiguity, this plan **fixes** the 6-step inputs as in §3.3 table, yielding `runs==4`.

### I20 Replay Attack

**Statement:** Replaying the bit-identical observation (same `observation_id`, `source_execution`, `root_task_id`, `model_family`, `retrieval_context_hash`, `canonical_source`) N times must not increase `validation_runs` or `confidence`, and `observation_id` must remain identical.

**Replay definition:** Same `H-888` with single base trace (`EXEC-REPLAY-1`, `LOOP-REPLAY-A`, `TASK-REPLAY`, `model=claude-sonnet-4`, `ctx=hash-0`) duplicated 5× and 10× by re-emitting identical trace YAMLs with same `execution_id`? No — to test dedup, we replay *logically identical* observations but with new `execution_id` yet same provenance tuple that I10/I11 should collapse: same `root_task_id`, same `(model_family, retrieval_context_hash)`, same `canonical_source` (if same loop) or at least same dedup keys. Two sub-cases:
- **Exact replay:** same `observation_id` string replayed (simulates log replay) → must not inflate
- **Logical replay:** new `execution_id`/`source_execution` but same `root_task_id`+`model`+`ctx`+`loop` → must collapse via I10/I11

**Expectation:** `runs` after 1 replay == `runs` after 5 replays == `runs` after 10 replays (all `1`), `confidence ==0.2` (single distinct source), `observation_id` unchanged.

---

## 3. Runtime Scenarios

### Case 1 — Long Horizon Simulation (I17)

**Scenario:** Simulate horizons 100, 500, 1000 observations mixed across hypothesis `H-888-ADVERSARIAL` and established `TASK-CTRL-001` (and optionally additional hypotheses to avoid single-memory bias). Distribution: 70% `reinforce_hypothesis` `observed` countable, 10% `reinforce_hypothesis` `inconclusive` (patched `term_matches=1`), 10% `weaken_hypothesis` `refuted` with `same_loop=true`, 10% established `reinforce` (on `TASK-CTRL-001`). All `root_task_id`/`model_family`/`retrieval_context_hash` made distinct per countable trace to avoid accidental I10/I11 collapse, except intentional duplicates to test dedup stability (10% of countable traces reuse prior `root_task_id`).

**Crafted input (per horizon H):**

```
For i in 0..H-1:
  if i % 10 == 0:  type=inconclusive (non-countable)
  elif i % 10 == 1: type=weaken same_loop
  elif i % 10 == 2: type=established reinforce (TASK-CTRL-001)
  else:            type=reinforce_hypothesis observed countable (H-888)
    - execution_id: EXEC-LH-{H}-{i}
    - loop_id: LOOP-LH-{H}-{i} (unique)
    - root_task_id: TASK-LH-{H}-{i} (unique except 10% reuse prior)
    - model: model-{i % 10}-unique  (distinct families)
    - hypotheses: [H-888, H-DUMMY-{i}] → distinct retrieval_context_hash per i
    - env_fingerprint: {"python_version":"3.14.4","collector_version":"8.7","model_family":model}
    - response: HIGH_QUALITY template + hypothesis mention (quality 4.8)
```

Established traces use `memories=[TASK-CTRL-001]` with `memory_influence=confirmation`.

**Expected artifacts:**
- For `H-888` at each horizon H:
  - `validation_runs ≈ 0.7*H * 0.9` (70% countable minus 10% intentional root reuse) with I10/I11 dedup applied; grows sub-linearly if horizon adds duplicates, not strictly linear
  - **Stability check:** `validation_runs(500) ≈ 5× validation_runs(100)` within ±10% (not drift); similarly `1000 ≈ 10×`
  - `confidence == 0.4` for all H≥2 (I14 cap) — not `1.0`
  - `negative_evidence_count ≈ 0.2*H` (inconclusive+weaken) tracked, `counter_evidence_ratio` ≈ countable/(countable+negative)
  - `evidence_independence` sizes match distinct counts
- For `TASK-CTRL-001`:
  - `validation_runs ≈ 0.1*H` distinct (`source_execution` distinct, no I10/I11)
  - `confidence == 1.0` (uncapped) or `min(runs/5,1.0)` per established rule

**Invariants:** I17

**PASS criteria:**

```python
# horizon 100, 500, 1000 results for H-888
for H, res in [(100, r100), (500, r500), (1000, r1000)]:
    assert res["validation_runs"] >= 2
    assert res["confidence"] == 0.4  # I14 cap holds at scale
    assert res["counter_evidence_ratio"] == round(res["validation_runs"] / (res["validation_runs"] + res["negative_evidence_count"]), 2)
# stability: allow 15% tolerance for intentional reuse jitter
assert abs(r500["validation_runs"] - 5 * r100["validation_runs"]) / (5 * r100["validation_runs"]) < 0.15
assert abs(r1000["validation_runs"] - 10 * r100["validation_runs"]) / (10 * r100["validation_runs"]) < 0.15
# established contrast
assert est_r1000["confidence"] == 1.0 or est_r1000["confidence"] == round(min(est_r1000["validation_runs"],5)/5,2)
```

**Performance observation (informational, not strict PASS unless regression):** wall time for H=1000 < 5× wall time for H=100.

---

### Case 2 — Memory Saturation (I18)

**Scenario:** 1000 distinct hypotheses `H-SAT-000` … `H-SAT-999`, each observed twice with distinct sources (to achieve `validation_runs==2` and `status==validated`). Plus a dedup probe: for 10 random hypotheses, emit a third observation reusing same `root_task_id` (should not inflate `runs`).

**Crafted input:**

```
For i in 0..999:
  hyp = H-SAT-{i:03d}  (created_loop=LOOP-ORIGIN)
  Trace A: EXEC-SAT-{i}-A, LOOP-SAT-{i}-A, TASK-SAT-{i}-A, model=claude-sonnet-4, hypotheses=[H-SAT-xxx, H-DUMMY-A-{i}] → ctxA
          response: HIGH_QUALITY + "Hypothesis H-SAT-xxx confirmed"
  Trace B: EXEC-SAT-{i}-B, LOOP-SAT-{i}-B, TASK-SAT-{i}-B, model=gpt-4, hypotheses=[H-SAT-xxx, H-DUMMY-B-{i}] → ctxB (distinct)
          response: same high quality

# Dedup probe for i in sample=[7, 42, 123, 256, 378, 451, 589, 734, 801, 999]:
  Trace C: EXEC-SAT-{i}-C, LOOP-SAT-{i}-C, TASK-SAT-{i}-A (reuse root of A), model=claude-sonnet-4, ctxA (same as A) → must collapse
```

Total traces: 2000 + 10 = 2010.

**Expected artifacts:**
- `len(groups) == 1000`
- For 990 hypotheses without probe: `validation_runs==2`, `confidence==0.4`, `status==validated`
- For 10 probed: `validation_runs==2` (not 3), `root_task_ids` count `2`
- No hypothesis has `validation_runs>2` despite 3 traces for probed
- `observation_id` distinct per observation (no clone)
- Runtime: `t_saturation < 2.0s` or `<5× t_100` (100-hyp baseline with 200 traces)

**Invariants:** I18, I10, I11, I14

**PASS criteria:**

```python
assert len(groups) == 1000
for mid, grp in groups.items():
    assert grp["validation_runs"] == 2
    res = val_by_id[mid]
    assert res["confidence"] == 0.4
    assert res["status"] == "validated"
# probe check
for i in probe_sample:
    mid = f"H-SAT-{i:03d}"
    assert val_by_id[mid]["validation_runs"] == 2
    assert len(val_by_id[mid]["evidence_independence"]["root_task_ids"]) == 2
# dedup: evidence_sources size 2 not 3
assert len(val_by_id["H-SAT-007"]["evidence_sources"]) == 2
# perf
assert t_saturation < 2.0  # seconds, informational threshold
```

---

### Case 3 — Adversarial Sequence Attack (I19)

**Scenario:** Ordered 6-step sequence targeting single `H-888-ADVERSARIAL` combining `reinforce`, `weaken`, `echo`, `drift`. Tests order-independence and combined invariant handling.

**Crafted input (fixed 6 steps):**

| Step | `execution_id` | `loop_id` | `root_task_id` | `model_family` (trace `model`) | `retrieval_context_hash` (via `hypotheses` list) | `influence_breakdown[H-888]` | `env_fingerprint` | Expected countable |
|------|----------------|-----------|----------------|-------------------------------|------------------------------------------------|-----------------------------|-------------------|-------------------|
| 1 | EXEC-SEQ-1 | LOOP-SEQ-1 | TASK-SEQ-1 | claude-sonnet-4 | ctx-1 (`[H-888, H-DUMMY-1]`) | `reinforce_hypothesis` `observed` `id_mentioned=true` `term_matches=3` | `{"python_version":"3.10.0","collector_version":"8.7","model_family":"claude-sonnet"}` | true |
| 2 | EXEC-SEQ-2 | LOOP-SEQ-2 | TASK-SEQ-2 | gpt-4 | ctx-2 (`[H-888, H-DUMMY-2]`) | `reinforce_hypothesis` `observed` | same `3.10.0` | true |
| 3 | EXEC-SEQ-3 | LOOP-SEQ-3 | TASK-SEQ-3 | claude-sonnet-4 | ctx-3 (`[H-888, H-DUMMY-3]`) | `weaken_hypothesis` `refuted` with `created_loop=LOOP-SEQ-3` → `same_loop=true` | same `3.10.0` | false (I9) |
| 4 | EXEC-SEQ-4 | LOOP-SEQ-4 | TASK-SEQ-4 | model-4-unique | ctx-4 (`[H-888, H-DUMMY-4]`) | `reinforce_hypothesis` `observed` | same `3.10.0` | true |
| 5 | EXEC-SEQ-5 | LOOP-SEQ-5 | TASK-SEQ-2 | gpt-4 | ctx-2 (repeat step2) | `reinforce_hypothesis` `observed` | same `3.10.0` | true but **collapsed** via I11 (same root+model+ctx as step2) |
| 6 | EXEC-SEQ-6 | LOOP-SEQ-6 | TASK-SEQ-6 | drift-model | ctx-6 (`[H-888, H-DUMMY-6]`) | `reinforce_hypothesis` `observed` | `{"python_version":"3.11.0","collector_version":"8.7","model_family":"drift-model"}` distinct → drift | true (distinct) |

Total log entries: 6. Distinct countable sources after I10/I11: steps 1,2,4,6 → 4. Step3 non-countable, step5 collapsed.

**Expected artifacts:**
- Observation log: 6 entries for `H-888`, `countable=[true,true,false,true,true,true]` but step5's `countable=true` yet validator will collapse it (log retains it, validator dedups). For log check, `countable` flags as above.
- Validation result for `H-888`:
  - `validation_runs == 4`
  - `negative_evidence_count == 1` (step3)
  - `counter_evidence_ratio == 0.80` (4 / (4+1) = 0.8)
  - `confidence == 0.4` (capped, not `0.8` or `1.0`)
  - `status == validated` (≥2 runs)
  - `staleness_warning == true` (step6 env differs)
  - `evidence_sources` size 4, contains `LOOP-SEQ-1,2,4,6` not `LOOP-SEQ-5`
  - `evidence_independence.root_task_ids == ["TASK-SEQ-1","TASK-SEQ-2","TASK-SEQ-4","TASK-SEQ-6"]` (4)
  - `model_families` count 4 (claude, gpt-4, model-4-unique, drift-model)
  - Echo check: `LOOP-SEQ-5` absent from `evidence_sources`

**Invariants:** I19 (combines I12, I11, I14, I16), plus I10

**PASS criteria:**

```python
log = [o for o in observation_log if o["memory_id"]=="H-888-ADVERSARIAL"]
assert len(log) == 6
assert [o["countable"] for o in log] == [True, True, False, True, True, True]
r = val_by_id["H-888-ADVERSARIAL"]
assert r["validation_runs"] == 4
assert r["negative_evidence_count"] == 1
assert r["counter_evidence_ratio"] == 0.8
assert r["confidence"] == 0.4  # I14 cap, not 0.8
assert r["status"] == "validated"
assert r["staleness_warning"] == True
assert "LOOP-SEQ-5" not in r["evidence_sources"]
assert len(r["evidence_sources"]) == 4
assert len(r["evidence_independence"]["root_task_ids"]) == 4
```

---

### Case 4 — Replay Attack (I20)

**Scenario:** Replaying the identical logical observation multiple times must not inflate distinct evidence count, confidence, or clone `observation_id`.

Two sub-cases executed sequentially:

**Sub-case A — Logical replay (same dedup keys, new execution):**
- Base observation: `EXEC-REPLAY-1`, `LOOP-REPLAY-A`, `TASK-REPLAY`, `model=claude-sonnet-4`, `hypotheses=[H-888, H-DUMMY-REPLAY]` → hash `hash-replay`, `observation_id=OBS-EXEC-REPLAY-1-H-888-ADVERSARIAL`
- Replays: `EXEC-REPLAY-2..5` (and later `..10`) each with **same** `root_task_id=TASK-REPLAY`, **same** `model_family=claude-sonnet-4`, **same** `retrieval_context_hash=hash-replay`, **same** `loop_id=LOOP-REPLAY-A` (so `canonical_source` identical) → must collapse via I10+I11

**Sub-case B — Exact log replay (same observation_id string):**
- Directly verify `observation_id` determinism: `OBS-{execution_id}-{hypothesis_id}` is recomputed per execution; replaying same `execution_id` yields same `observation_id`, but new `execution_id` yields new `observation_id` — validator must still collapse via provenance keys, not `observation_id` equality alone.

**Crafted input:**

```
For N in [1, 5, 10]:
  Generate N traces:
    execution_id: EXEC-REPLAY-{i}  (i=1..N, distinct)
    loop_id: LOOP-REPLAY-A (same for all)
    root_task_id: TASK-REPLAY (same)
    model: claude-sonnet-4-20250514 (same)
    hypotheses: [H-888-ADVERSARIAL, H-DUMMY-REPLAY] (same → same hash)
    influence_breakdown[H-888]: reinforce_hypothesis observed id_mentioned=true
    env_fingerprint: same {"python_version":"3.10.0","collector_version":"8.7","model_family":"claude-sonnet"}
```

**Expected artifacts (per N):**
- `validation_runs == 1` for `H-888` for N=1,5,10 (identical)
- `confidence == 0.2` (1/5) for all N (no inflation)
- `observation_id` for first trace `OBS-EXEC-REPLAY-1-H-888-ADVERSARIAL` distinct from later traces' `OBS-EXEC-REPLAY-2-...` but validator still counts 1 distinct source; log has N entries each with distinct `observation_id` yet validator collapses to 1
- Evidence independence: `root_task_ids==1`, `model_families==1`, `context_hashes==1`

**Invariants:** I20, I10, I11, I13, I14

**PASS criteria:**

```python
for N in [1, 5, 10]:
    r = run_pipeline(N_replays)["val_by_id"]["H-888-ADVERSARIAL"]
    assert r["validation_runs"] == 1, f"N={N} should stay 1, got {r['validation_runs']}"
    assert r["confidence"] == 0.2
    assert r["observation_id"] == "OBS-EXEC-REPLAY-1-H-888-ADVERSARIAL"  # result carries first observed
    assert len(r["evidence_sources"]) == 1
    assert len(r["evidence_independence"]["root_task_ids"]) == 1
# cross-N stability
assert val_N1["validation_runs"] == val_N5["validation_runs"] == val_N10["validation_runs"]
assert val_N1["confidence"] == val_N5["confidence"] == val_N10["confidence"]
# log has N distinct observation_ids but still collapsed
log_N10 = [o for o in log_N10 if o["memory_id"]=="H-888-ADVERSARIAL"]
assert len(log_N10) == 10
assert len({o["observation_id"] for o in log_N10}) == 10  # log preserves distinct ids
assert len({o["canonical_source"] for o in log_N10}) == 1  # but canonical source collapsed
```

---

## 4. Validation Matrix

| Case | Attack | Horizon / Input | Invariant | Expected Artifact | PASS Criteria |
|------|--------|-----------------|-----------|-------------------|---------------|
| 1 | Long Horizon | 100/500/1000 mixed traces (`H-888` + `TASK-CTRL-001`) | I17 Long Horizon Stability | `validation_runs` ∝ distinct sources, `confidence==0.4`, `ratio` stable | `runs(500)≈5×runs(100)` ±15%, `conf==0.4` at all H≥2 |
| 2 | Saturation | 1000 hyps ×2 +10 probes =2010 traces | I18 Saturation | `len(groups)==1000`, each `runs==2`, `conf==0.4`, probe `runs==2` not 3, `t<2s` | Groups 1000, probe dedup, runtime bounded |
| 3 | Adversarial Sequence | 6-step `reinforce→reinforce→weaken→reinforce→echo→drift` | I19 Sequence | log 6, `countable` `[T,T,F,T,T,T]` but `runs==4`, `negative==1`, `ratio==0.8`, `conf==0.4`, `staleness==true`, echo absent | `runs==4`, `negative==1`, `ratio==0.8`, `conf==0.4`, echo collapsed |
| 4 | Replay | N=1,5,10 identical logical replay | I20 Replay | `runs==1`, `conf==0.2`, `observation_id` stable, log N distinct ids but 1 source | `runs` unchanged across N, `conf` unchanged |

---

## 5. Runtime Constraints

### 5.1 Mandatory Constraints

| Constraint | Detail |
|------------|--------|
| **No code modification** | Zero changes to any `.py` — validation is read-only pipeline consumption. |
| **No frozen surface mutation** | `promoter.py`, `retrieval_optimizer.py`, `retrieval_adapter.py`, `prompts/`, benchmark templates untouched; verify via `git diff --name-only HEAD` |
| **No memory lifecycle change** | No promotion/demotion, no `memory-observation-log.yaml` or `validation-results.yaml` production writes |
| **Validation artifacts only** | Output is `Phase-8.8-Stress-Validation-Report.md` + isolated temp trace/log YAMLs |
| **Isolated environment** | Temp `TRACES_DIR`, temp `OBSERVATION_LOG_FILE`, temp `CANDIDATES_FILE`, `update_state=False`, `validator.OBSERVATION_LOG_FILE` patched to temp |

### 5.2 Validation Environment

| Setting | Value |
|---------|-------|
| Working directory | ` /home/shade/.agents/runtime/loop-controller` but all I/O via `tempfile.TemporaryDirectory()` |
| Observation log | Temp file (not `memory-observation-log.yaml`) |
| Candidates file | Temp file (not `memory-candidates.yaml`) |
| Validation results | In-memory `validate_candidates()` return + temp `validation_out.yaml` for checksum |
| State file | Disabled (`update_state=False`, `collector_state.yaml` not updated) |
| Response quality | High-quality template (headers, bullet, code block, Chinese keywords → `quality_score 4.8`) to pass `QUALITY_THRESHOLD 3.0` |

### 5.3 Pipeline Stages Used

```
build_trace(execution_id, trace_id, task_id, decision_context, model, runtime_result, loop_id)
  → write trace YAML to temp TRACES_DIR
  → collect_from_trace_ids(trace_ids, quiet=True, update_state=False)
  → validate_candidates(candidates, quiet=True)
  → read temp observation log
```

- `runtime_adapter.build_trace` must provide Phase 8.7 fields: `root_task_id`, `model_family`, `retrieval_context_hash`, `env_fingerprint`, `observation_id`
- `collector` must log ALL observations with `countable` flag (I12) and propagate `root_task_id`/`model_family`/`retrieval_context_hash`
- `validator` enforces I10/I11 dedup via `seen_root_tasks`/`seen_model_contexts`, I14 cap `min(runs,2)/5`, I16 `staleness_warning`

---

## 6. OpenCode Execution Brief

### Task: Phase 8.8 Stress Validation — Plan Only (this document)

**This phase outputs only the plan.** No pipeline execution yet.

**Next phase** (Phase 8.8 execution) will consume this plan to run 4 cases in isolated temp dirs and produce `benchmark-8.8/Phase-8.8-Stress-Validation-Report.md`.

### Report Requirements (for execution phase)

Execution must produce `benchmark-8.8/Phase-8.8-Stress-Validation-Report.md` containing:

1. **Summary** PASS/FAIL table for I17-I20 (4 cases)
2. **Per-case details:** attack description, input summary (counts, horizons), expected artifact, actual artifact (JSON excerpts), verdict
3. **Artifact locations:** persist dirs of temp YAMLs
4. **Artifact checksums:** `sha256(file)[:16]` for log/candidates/validation per case
5. **Perf metrics:** I17 horizon wall times (100/500/1000), I18 saturation wall time vs 100-hyp baseline
6. **Regression check:** `67/67` existing tests still PASS (command & output)
7. **Frozen surface check:** `git diff --name-only HEAD -- promoter.py retrieval_optimizer.py retrieval_adapter.py prompts/` → no output

### Regression Command (to be run in execution phase)

```bash
cd /home/shade/.agents/runtime/loop-controller
pytest tests/test_phase_8_7_integrity.py tests/test_phase_8_6_hypothesis_safety.py tests/test_phase_8_4_hypothesis_reinforcement.py tests/test_phase_8_5_integration.py -q
# Expected: 67 passed
```

### Frozen Surface Verification (to be run in execution phase)

```bash
git diff --name-only HEAD -- \
  runtime/memory-feedback/promotion/promoter.py \
  runtime/memory-feedback/retrieval/retrieval_optimizer.py \
  runtime/loop-controller/retrieval_adapter.py \
  prompts/
# Expected: no output
```

---

## 7. Backward Compatibility & Risk

| Risk | Mitigation |
|------|------------|
| Long horizon log cap `OBSERVATION_LOG_MAX_PER_MEMORY=20` may prune horizon 1000 tail | Stress validation uses temp isolated log (not production cap) or asserts `prune_observation_log` keeps last 20 but validator enrichment `enrich_groups_with_observation_log` synthesizes correctly; document cap behavior as informational, not failure |
| Saturation 2010 traces memory | Isolated temp dir per case, streaming write, not bulk in production `TRACES_DIR` |
| Hypothesis quality threshold `3.0` flaking at scale | Use proven HIGH_QUALITY template (`quality_score 4.8`) for all crafted traces |
| Frozen surface accidental edit during stress harness | `git diff --name-only` guard runs pre/post; harness asserts no `.py` diff |

---

**Phase 8.8 Stress Validation Plan v1 — Ready for OpenCode execution (validation only, no code).**
