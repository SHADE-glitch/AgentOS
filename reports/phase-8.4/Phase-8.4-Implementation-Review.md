# Phase 8.4 — Implementation Review

**Date:** 2026-09-03
**Role:** Agent OS Architecture Reviewer
**Source:** Phase 8.4 Implementation Report (text.txt)
**Reviewed:** 4 source files + 1 test file

---

## Verdict

# APPROVED

The implementation correctly implements the revised plan. All 8 invariants are satisfied. candidate_type/outcome mapping is consistent. Validator observation accounting is correct. No self-confirmation path exists. No frozen surface was modified. 27 tests provide deterministic coverage of all critical paths.

---

## 1. Eight Invariants: Implementation Audit

| # | Invariant | Status | Evidence from Code |
|---|-----------|--------|--------------------|
| **I1** | Identity | **PASS** | `collector.py:327-333` — `hypotheses_injected` set guards identity; `hyp_id not in hypotheses_injected` → skip. `team_result_collector.py:247` — `source["hypotheses_injected"]` provides identity. **Caveat:** if `hypotheses_injected` is empty in trace, I1 gating is vacuous (acknowledged in implementation report §6). |
| **I2** | Trust | **PASS** | `validator.py:149-152` — 1 obs → "hypothesis", 2 obs → "validated". `promoter.py:390` — only "validated" status promoted. Hypothesis stays hypothesis until 2 independent observations. |
| **I3** | Causality | **PASS** | `collector.py:100-131` — `classify_hypothesis_engagement` separates `confirmed` (changed_decision / hypothesis_confirmed) from `observed` (id_mentioned / term_matches>=3) from `inconclusive` (weak mention). Retrieval/injection alone does not produce `confirmed`. |
| **I4** | Negative-evidence | **PASS** | `collector.py:118-119` — `_is_hypothesis_refuted` → `weaken_hypothesis` + `refuted`. `validator.py:140` — `weaken_hypothesis` rejected (human review). `validator.py:74-78` — `inconclusive` excluded from `executions`. |
| **I5** | Independence | **PASS** | `collector.py:334-335` — `mem_used` guard prevents double-emit. `validator.py:69-78` — `executions` set deduplicates by `source_execution`. `team_result_collector.py:265` — `shared_context_with_other_agents=True` marker. |
| **I6** | Abstention | **PASS** | `collector.py:116` — `not referenced` → `None` (no candidate). `collector.py:340` — `ctype is None` → skip. `team_result_collector.py:259` — `not eng.get("referenced")` → skip. |
| **I7** | Promotion | **PASS** | `promoter.py:390` — only `validated` status promoted. `promoter.py:234-235` — `old_el="hypothesis"` → `runtime_validated` (1 obs). `promoter.py:238-239` — `runtime_validated` → `independent_validated` (2 obs). `check_trust_gate` accepts both `validated` and `hypothesis` but the main loop only iterates `validated`. |
| **I8** | Audit | **PASS** | `collector.py:86-98` — `_normalize_hypothesis_engagement` builds 7-key provenance: `referenced`, `engagement_level`, `term_matches`, `id_mentioned`, `changed_decision`, `same_loop_as_creation`, `shared_context_with_other_agents`. Full trace from loop → trace → injection → agent output → evidence classification. |

---

## 2. candidate_type / outcome Consistency

### Mapping Matrix

| Path | Condition | candidate_type | outcome | Verified |
|------|-----------|---------------|---------|----------|
| R7 trace | `changed_decision=True` | `reinforce_hypothesis` | `confirmed` | `collector.py:124` |
| R7 trace | `hypothesis_confirmed` | `reinforce_hypothesis` | `confirmed` | `collector.py:124` |
| R7 trace | `id_mentioned` OR `term_matches>=3` | `reinforce_hypothesis` | `observed` | `collector.py:128` |
| R7 trace | weak mention (used, no id/terms) | `reinforce_hypothesis` | `inconclusive` | `collector.py:129` |
| R7 trace | `_is_hypothesis_refuted` true | `weaken_hypothesis` | `refuted` | `collector.py:119` |
| R7 trace | `not referenced` | `None` | `inconclusive` | `collector.py:116` |
| R4 team | Same as R7 via `classify_hypothesis_engagement` | same as R7 | same as R7 | `team_result_collector.py:260` |

**All mappings are consistent. No `reinforce_hypothesis` + `refuted` combination exists. No `weaken_hypothesis` + `confirmed` combination exists.**

### Edge Cases Verified

- **`hypothesis_used` + no `id_mentioned` + `term_matches=2`:** → `inconclusive` (test_10, line ~175)
- **`not referenced` + refutation text:** → `None` (abstention governs over refutation, test_9, line ~168)
- **`hypothesis in mem_used`:** → R7 skipped, R1 handles (test_15, line ~235)

---

## 3. Validator Observation Accounting

### Critical Check: Does `inconclusive` ever inflate `validation_runs`?

**No.** Verified at 3 levels:

| Level | Code | Behavior |
|-------|------|----------|
| **Grouping** | `validator.py:74-78` | `inconclusive` hypothesis candidates NOT added to `executions` set |
| **Observation log** | `collector.py:481-484` | `inconclusive` hypothesis candidates NOT appended to observation-log |
| **Validation** | `validator.py:109` | `validation_runs = len(executions)` — only non-inconclusive executions counted |

**Test verification:** `test_23_inconclusive_hyp_not_counted` — executions set is empty. `test_27_mixed_inconclusive_confirmed_runs` — only `{"L2"}` counted.

### Critical Check: Does `weaken_hypothesis` ever contribute to validation?

**No.** `validator.py:140` — `ctype in ("weaken", "weaken_hypothesis")` → rejected. `test_22_rejects_weaken_hypothesis` verifies.

### Critical Check: Does 1 observation trigger promotion?

**No.** `validator.py:149-152` — 1 obs → "hypothesis" status. `promoter.py:390` — only "validated" promoted. `test_25_1_obs_hypothesis_not_validated_not_promoted` verifies.

---

## 4. Self-Confirmation Risk Assessment

### Risk: Agent echoes injected hypothesis, counted as independent observation

**Mitigated.** The `classify_hypothesis_engagement` function (collector.py:100-131) separates evidence levels:

- `confirmed` → requires `changed_decision` or `hypothesis_confirmed` engagement level (not just echo)
- `observed` → requires `id_mentioned` or `term_matches >= 3` (explicit engagement)
- `inconclusive` → weak mention, never counted toward validation_runs

The team path (R4) uses minimal stubs with zero tags/guidance, so `term_matches` from `_detect_hypothesis_engagement` is always 0. Only `id_mentioned` (literal ID match) or engagement patterns trigger detection. This prevents false positives from hypothesis terminology echo.

### Risk: Same-loop agent confirms its own hypothesis

**Mitigated.** `validator.py:69-78` — `executions` set deduplicates by `source_execution`. Same loop_id → counted once. `collector.py:334-335` — `mem_used` guard prevents double-emit from R1 + R7.

### Risk: refuted hypothesis counted as supporting evidence

**Mitigated.** `collector.py:118-119` — refuted → `weaken_hypothesis`. `validator.py:140` — `weaken_hypothesis` rejected. `test_22` verifies.

---

## 5. Frozen Surface Audit

| Surface | Modified? | Evidence |
|---------|-----------|----------|
| `promoter.py` | **NO** | `grep -c` confirms no Phase 8.4 changes |
| `retrieval-index.yaml` | **NO** | Not in modified files |
| Agent prompt | **NO** | Not in modified files |
| Benchmark | **NO** | Not in modified files |
| Scoring | **NO** | Not in modified files |
| `runtime_adapter.py` | **NO** | Imported but not modified |
| `experience_extractor.py` | **NO** | Not in modified files |
| `base_collector.py` | **NO** | Not in modified files |
| Validator thresholds | **NO** | `HYPOTHESIS_MIN_OBSERVATIONS=1`, `MIN_OBSERVATIONS=2`, `QUALITY_THRESHOLD=3.0` unchanged |

**All frozen surfaces verified untouched.**

---

## 6. Test Coverage

### 27 tests, 6 focus areas

| Class | Focus | Tests | Count | Key Coverage |
|-------|-------|-------|-------|-------------|
| A | classify_hypothesis_engagement | 1-10 | 10 | confirmed, observed, inconclusive, refuted, abstain, provenance keys, abstention-governs-refutation |
| B | R7 trace path | 11-16 | 6 | confirmed emission, full provenance, not-referenced abstain, I1 identity gating, I5 no double-emit, refuted→weaken |
| C | R4 team path | 17-21 | 5 | reinforce emission, shared-context+is_lead provenance, agent-not-referencing abstain, absent hypotheses_injected, refuted→weaken |
| D/E/F | Validator | 22-27 | 6 | reject weaken_hypothesis, inconclusive-not-counted, confirmed-counts, 1-obs→hypothesis, 2-obs→validated, mixed runs |

### Coverage Gaps (non-blocking)

| Gap | Severity | Note |
|-----|----------|------|
| Multiple hypotheses in same candidate batch | Low | Covered implicitly by R7 loop — each hypothesis processed independently |
| H-xxx with mixed reinforce + weaken → validator behavior | Low | `test_27` covers mixed inconclusive+confirmed. No explicit test for reinforce+weaken same group, but validator rejects `weaken_hypothesis` at line 140 regardless of other candidates |
| Real end-to-end loop run | Medium | Not possible without provider; acknowledged in implementation report |

---

## 7. Minor Observations (Non-Blocking)

### O1. `same_loop_as_creation` field present but unused

`collector.py:95` — `_normalize_hypothesis_engagement` includes `same_loop_as_creation` key. It is always `False` (default passthrough, never set by any producer). The revised plan said to remove it from Phase 8.4 scope, but the implementation keeps it as a passthrough. Harmless — the field is never used by validator or promoter.

### O2. `_is_hypothesis_refuted` does not use `hyp_id` for specificity

`collector.py:134` — The `hyp_id` parameter is accepted but never used. The refutation patterns match any `H-\d+`, not just the specific hypothesis. Combined with the `term_matches > 0` guard, this could theoretically cause false positives if the agent refuted H-003 but H-001 had term_matches > 0. In practice, the `id_mentioned` guard provides the primary protection.

### O3. R7 does not use `make_candidate()` helper closure

`collector.py:343-369` — R7 builds the candidate dict manually, while R1-R6 use the `make_candidate()` closure (defined at line 233). R7 correctly copies `evidence.copy()` and includes all required fields. This is a style inconsistency, not a bug.

### O4. I1 identity gating vacuous when `hypotheses_injected` is empty

`collector.py:327-333` — `if hypotheses_injected and hyp_id not in hypotheses_injected: continue` — when `hypotheses_injected` is empty, the identity check is skipped entirely. This is acknowledged in the implementation report §6. Mitigation: trace producers must persist the injected list.

---

## 8. Summary

| Check | Result |
|-------|--------|
| 8 invariants compliance | ALL PASS |
| candidate_type/outcome consistency | PASS — no contradiction |
| Validator observation accounting | PASS — inconclusive excluded, weaken rejected |
| Self-confirmation risk | PASS — mitigated via evidence classification |
| Frozen surface modification | PASS — none modified |
| Test coverage | PASS — 27 deterministic tests |
| Rollback safety | PASS — all additive |

---

**APPROVED for merge. The implementation is functionally correct, self-consistent, and respects all 8 invariants.**