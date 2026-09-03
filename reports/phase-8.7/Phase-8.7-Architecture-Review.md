# Phase 8.7 Architecture Review — Adversarial Memory Integrity

**Date:** 2025-09-03
**Auditor:** Agent OS Architecture Engineer
**Scope:** Post-Phase-8.6 Runtime Closure — Adversarial Memory Integrity Review
**Basis:** `benchmark-8.6/Phase-8.6-Architecture-Review.md` (APPROVED) + `benchmark-8.6/Phase-8.6-Implementation-Report.md` + `Phase-8.6-Runtime-Validation-Report.md` (PASS) + source audit of `collector.py`, `validator.py`, `promoter.py`, `retrieval_optimizer.py`, `retrieval_adapter.py`, `runtime_adapter.py`
**Verdict:** **APPROVED FOR IMPLEMENTATION — Phase 8.7 may proceed under the invariant and frozen-surface constraints defined herein**

---

## 0. Executive Summary

Phase 8.6 closed the hypothesis safety layer: C1-C5 all PASS, 56/56 tests green, self-confirmation (I9) and cross-type contamination (C3) now enforced with real provenance. The system now has a correct per-loop counting model for hypothesis validation.

However, the current trust model is **content-agnostic and structurally vulnerable**. Phase 8.6 validates that evidence is *structurally independent* (distinct loops) but does not validate that evidence is *substantively correct* (factually grounded). The eight threats analyzed below reveal that the promotion pipeline can be gamed through:

1. **Content poisoning** — structurally valid but factually wrong hypotheses
2. **Evidence fan-out** — derived artifacts masquerading as independent evidence
3. **Retrieval rank capture** — exposure bias creating unfair promotion advantage
4. **Promotion-retrieval feedback** — uncontrolled trust amplification through positive feedback
5. **Multi-agent echo** — shared context creating false independence
6. **Counter-evidence loss** — negative evidence vanishing from the pipeline
7. **Temporal drift** — old valid memories becoming harmful after environment change
8. **Observation identity fragmentation** — different components disagreeing about the same observation

Phase 8.7 is proposed as a **purely additive integrity layer** — no changes to the counting model, no removal of Phase 8.6 invariants, no touching of frozen surfaces (promoter, retrieval_optimizer, retrieval_adapter, prompts, templates). The implementation adds observation-level integrity checks, evidence diversity metadata, and audit-only negative-evidence preservation — all reversible, testable, and backward compatible.

---

## 1. Current System Boundary After Phase 8.6

### 1.1 Defenses in place

| Layer | Defense | Mechanism | Phase |
|-------|---------|-----------|-------|
| **Structural** | Execution dedup | `set(source_execution)` in `group_candidates_by_memory` | 8.4 |
| **Structural** | Loop dedup (hypothesis) | `set(canonical_source)` with `canonical_source_for()` priority chain | 8.6-C4 |
| **Structural** | Self-confirmation exclusion | `same_loop_as_creation` provenance + `is_countable_observation` gate | 8.6-C1/C5 |
| **Structural** | Inconclusive exclusion | `is_countable_observation` rejects `outcome==inconclusive` for hypothesis types | 8.4/8.6-C5 |
| **Structural** | Cross-type rejection | C3 fail-closed type guard: `reinforce→H-xxx` and `reinforce_hypothesis→non-H` rejected | 8.6-C3 |
| **Structural** | Distinct-loop threshold | Hypothesis `validated` requires ≥2 distinct canonical sources | 8.6-C2 |
| **Quality** | Quality threshold | `best_qs >= QUALITY_THRESHOLD (3.0)` gate in `validate_memory_group` | 5.7 |
| **Quality** | Trust Gate M1-M6 | Provenance, evidence level, duplicate, confidence, relevance, staleness checks in `promoter.py` | 5.11 |
| **Retrieval** | Two-pass separation | Established scored by `final_score`, hypotheses by `static_relevance`; cap at 5 | 8.2.1.5 |
| **Retrieval** | Hypothesis labeling | `[UNVALIDATED]` / `⚠` guidance in injection prompt | 8.2.1 |
| **Lifecycle** | Graduation | `hypothesis → runtime_validated → independent_validated` progression in `promoter.py` | 8.2.1.1 |

### 1.2 Trust boundaries

The system has **two trust boundaries**:

1. **Content boundary:** Between the raw trace data (agent output, task text, execution context) and the memory system's internal counting/evaluation. The counting layer (validator) trusts that `outcome`, `quality_score`, and `candidate_type` reflect ground truth. There is no content-level verification of the agent's claim.

2. **Promotion boundary:** Between `validator` (counting/structural) and `promoter` (lifecycle/file-system-mutation). The promoter trusts that `validated` status means the evidence is sufficient and correct. The promoter's Trust Gate M1-M6 checks metadata provenance but does not verify evidence content.

### 1.3 What Phase 8.6 does NOT defend against

- **Factually wrong but structurally valid hypotheses** — a hypothesis with 2 distinct-loop observations, high quality scores, and correct candidate types can still be promoted even if it is factually incorrect
- **Evidence derivation chains** — two observations from the same root event (e.g., a trace and its team summary) count as independent
- **Retrieval-driven amplification** — memories retrieved more often get more usage, more evidence, and higher promotion probability
- **Counter-evidence erasure** — `weaken`/`weaken_hypothesis` candidates are rejected at validator, and inconclusive observations are excluded from counting — but neither is preserved for audit
- **Temporal invalidation** — a memory validated under Python 3.12 may be harmful under Python 3.14 but the system has no staleness re-evaluation trigger

---

## 2. Remaining Trust Boundary Gaps

| Gap ID | Gap | Trust Boundary | Severity |
|--------|-----|---------------|----------|
| G1 | **Content trust** — no verification that agent claims about hypothesis correctness are grounded in task output | Content boundary | HIGH |
| G2 | **Evidence lineage** — no tracking of whether two observations derive from the same root event | Content boundary | MEDIUM |
| G3 | **Retrieval fairness** — no mechanism to prevent retrieval-frequency bias from creating promotion advantage | Promotion boundary | MEDIUM |
| G4 | **Feedback amplification** — no damping of the retrieval→usage→evidence→promotion→retrieval loop | Promotion boundary | MEDIUM |
| G5 | **Agent independence** — no verification that corroborating agents are causally independent | Content boundary | MEDIUM |
| G6 | **Negative evidence retention** — `weaken`/`inconclusive` candidates are discarded, not preserved | Content boundary | LOW-MEDIUM |
| G7 | **Temporal validity** — no mechanism to re-evaluate memories after environment changes | Promotion boundary | LOW |
| G8 | **Observation identity** — different pipeline components use different identifiers for the same observation | Content boundary | LOW |

---

## 3. Threat Model Evaluation

### 3.1 Seeded Hypothesis Poisoning

**Attack description:**
A structurally valid but factually wrong H-xxx hypothesis is created by the resolver. The hypothesis has correct metadata (tags, category, source_task), passes all structural gates, and receives 2 distinct-loop observations because agents in later loops confirm it (either due to the same incorrect reasoning, or because the hypothesis text is persuasive but wrong). The hypothesis graduates to `validated` and is promoted to `runtime_validated`, entering the established retrieval pool.

**Current defense:**
- Quality threshold (`best_qs >= 3.0`) — but quality score is a proxy for "agent produced coherent output," not "agent produced correct output"
- `is_countable_observation` excludes inconclusive and self-confirm — but `observed` with high quality is still counted
- Trust Gate M1-M6 — checks provenance, not content truth
- Two-loop threshold — requires cross-loop confirmation, but agents in different loops can all be wrong about the same thing

**Remaining weakness:**
The system has **no content-level verification boundary**. It cannot distinguish between "agent A and agent B independently confirmed the hypothesis is correct" and "agent A and agent B independently confirmed the same wrong hypothesis because the underlying model has the same bias."

**Required invariant:**
**Content-Bounded Trust Invariant (proposed):** A hypothesis SHALL NOT be promoted to `validated` unless at least one observation includes evidence that the hypothesis changed the agent's decision in a way that led to a task success. This is a weaker form of the existing `changed_decision` field — the system already tracks it, but does not require it for promotion.

**Implementation impact:**
- **LOW** — Add a check in `_build_result` that `changed_decision==true` for at least one observation when hypothesis is promoted to `validated`. This is additive, uses existing provenance, and is backward compatible (hypotheses without `changed_decision` observations stay at `hypothesis` status).
- Collector already carries `changed_decision` in `hypothesis_engagement`.
- No frozen surface mutation.

---

### 3.2 Evidence Fan-Out Contamination

**Attack description:**
A single root event (e.g., one task execution in loop L) produces multiple derived artifacts:
- The agent's own trace (R7 individual) → `reinforce_hypothesis` candidate
- The team lead's summary (R4 team) → `reinforce_hypothesis` candidate
- A downstream agent that re-uses the summary → another `reinforce_hypothesis` candidate

These three artifacts have different `source_execution` values and potentially different `canonical_source` values (if the team result has its own loop_id), but they all derive from the same root event. The validator counts them as independent evidence.

**Current defense:**
- `canonical_source` normalization (C4) — collapses same-loop executions to one
- `source_loop` dedup in `enrich_groups_with_observation_log` — prevents same-loop double-count from log
- Candidate ID prefix (`CAND-{eid}-HYP-` vs `CAND-{loop_id}-LEAD-HYP-`) — makes provenance traceable

**Remaining weakness:**
Two different `canonical_source` values can still trace back to the same root event. For example, `LOOP-A` (individual) and `LOOP-A-TEAM` (team summary of same loop) are different loop IDs but the same logical event. The system has no "root event identity" concept.

**Required invariant:**
**Evidence Independence Invariant:** Two observations of the same hypothesis SHALL NOT be counted as independent if they derive from the same root task execution. Observations are independent only if they originate from different task executions with different task texts.

**Implementation impact:**
- **MEDIUM** — Requires adding `root_task_id` or `root_execution_id` to observation log entries. The collector already has access to `task_id` from trace context. Two observations with the same `root_task_id` would be collapsed to one canonical source.
- **Alternative (lower impact):** Add `root_execution_id` to observation log and check in `enrich_groups_with_observation_log` / `synthesize_groups_from_observation_log`. Count distinct `root_execution_id` values instead of distinct `source_loop` values for hypothesis lane.
- No frozen surface mutation. Collector and validator only.

---

### 3.3 Retrieval Rank Capture

**Attack description:**
A hypothesis that is frequently retrieved (due to high `static_relevance` score from tag matching, or due to top-K concentration) gets more agent exposure, more usage, more `reinforce_hypothesis` candidates, and thus a higher probability of reaching `validated`. Hypotheses that are equally correct but less frequently retrieved (due to niche tags, lower static_relevance, or being pushed out of top-K by more popular hypotheses) get fewer chances to accumulate evidence.

**Current defense:**
- Two-pass retrieval separates hypothesis scoring from established scoring
- Hypothesis injection cap at 5 (`_MEMORY_INJECTION_LIMIT`)
- `static_relevance` is task-text-driven, not promotion-driven
- Multiplicative scoring model prevents quality-gaming of established ranking

**Remaining weakness:**
- No mechanism to ensure retrieval diversity across hypothesis population
- Top-K concentration: the same 5 hypotheses dominate retrieval, starving others
- No "retrieval fairness" metric — the system doesn't track how many times each hypothesis has been retrieved vs. how many observations it has accumulated
- Tag manipulation: a hypothesis with broad, high-frequency tags gets more retrieval exposure than a narrow, specific hypothesis

**Required invariant:**
**Retrieval Diversity Invariant:** Over any rolling window of N retrievals, no single hypothesis SHALL account for more than 50% of hypothesis injections, and at least 3 distinct hypotheses SHALL be injected across the window.

**Implementation impact:**
- **LOW-MEDIUM** — Add a `retrieval_history` check in `retrieval_adapter.py` or `runtime_adapter.py` before injection. Track the last N retrievals and compute a diversity score. If a hypothesis exceeds the 50% threshold, downgrade its injection priority or skip it.
- **Alternative (lower impact, no frozen surface):** Add diversity metadata to observation log (e.g., `retrieval_rank`, `injection_position`) and surface in validation audit. No enforcement — auditing only, leaving enforcement to a future phase.
- The retrieval_adapter is currently a frozen surface. The diversity check would be in `runtime_adapter.py` (injection logic) or `collector.py` (candidate generation), not in `retrieval_adapter.py` or `retrieval_optimizer.py`.

---

### 3.4 Promotion-Retrieval Feedback Loop

**Attack description:**
The pipeline creates a positive feedback loop:
1. Hypothesis is retrieved frequently → more agent exposure
2. More agent exposure → more `reinforce_hypothesis` candidates
3. More candidates → higher probability of reaching `validated`
4. `validated` → promoted to `runtime_validated` → higher `evidence_level`
5. Higher `evidence_level` → higher `adaptive_score` in retrieval (through `confidence_score` component)
6. Higher score → more retrieval → more exposure → loop amplifies

This can create uncontrolled trust amplification where a hypothesis that was initially weak becomes "validated" primarily through exposure frequency, not through evidence quality.

**Current defense:**
- Multiplicative scoring: `static_relevance` is primary, quality bonus capped at 30%
- Two-pass retrieval prevents hypothesis quality from polluting established ranking
- `evidence_level` impacts `confidence_score` indirectly through `observation_count`, but the quality bonus is capped
- Hypothesis injection cap at 5

**Remaining weakness:**
- The `observation_count` used in `compute_adaptive_score` (via `confidence_score`) is the same metric that triggers promotion. This creates a direct feedback path: more observations → higher confidence_score → higher retrieval score → more observations.
- No damping mechanism — the loop is open-ended
- `static_relevance` is fixed for a given task text, but `confidence_score` grows with each observation

**Required invariant:**
**No Positive Feedback Promotion Invariant:** The promotion of a hypothesis to `validated` or `runtime_validated` SHALL NOT increase its retrieval score. The retrieval score of a hypothesis SHALL be determined solely by `static_relevance` (content match) and capped at its initial value.

**Implementation impact:**
- **LOW** — This is largely already satisfied by the multiplicative scoring model. The remaining gap is `confidence_score` growth from `observation_count`. Fix: for hypothesis-type memories, freeze `confidence_score` at the value at time of creation (or cap at initial value). This is a one-line change in `compute_adaptive_score` in `retrieval_optimizer.py`.
- **BUT:** `retrieval_optimizer.py` is a frozen surface. This invariant must be enforced elsewhere — specifically in `runtime_adapter.py` injection logic (don't boost injection priority for promoted hypotheses) or in `collector.py` (don't use post-promotion confidence in candidate quality).
- **Alternative (no frozen surface):** Enforce the invariant in `validator.py` by not using `observation_count` growth for hypothesis confidence scoring; instead, use a fixed initial confidence. This is within allowed files.

---

### 3.5 Multi-Agent Echo Chamber

**Attack description:**
Multiple agents in the same team or across loops agree on the same retrieved hypothesis, creating the appearance of independent confirmation. However, the agents share:
- **Same retrieval context** — all agents received the same `hypotheses_injected` set
- **Same upstream summary** — the team lead's summary is shared across agents
- **Same prompt lineage** — all agents use the same prompt template with the same hypothesis guidance
- **Same model family** — all agents use the same underlying model, inheriting the same biases

The validator counts these as independent observations (different `source_execution`, different `agent`), but the agents are not causally independent.

**Current defense:**
- `canonical_source` normalization (C4) — same-loop agents share the same `canonical_source`
- Team lane `shared_context_with_other_agents` marker — identifies team-derived observations
- No team+individual double-count (different `canonical_source` values but same root — see §3.2)

**Remaining weakness:**
- Cross-loop agents in different loops get different `canonical_source` values, but they may still share the same hypothesis set, same model, and same prompt template
- No tracking of `model_family`, `prompt_template_hash`, or `retrieval_context_hash` in observation provenance
- No requirement that corroborating agents use different models or different retrieval contexts

**Required invariant:**
**Causal Independence Invariant:** Two observations of the same hypothesis SHALL NOT be counted as independent if they originate from the same model family AND the same retrieval context (same `hypotheses_injected` set hash). At least one of these dimensions must differ for observations to be considered independent.

**Implementation impact:**
- **LOW** — Add `model_family` and `retrieval_context_hash` to observation log entries. In `enrich_groups_with_observation_log`, compute a diversity score: if two observations share both `model_family` and `retrieval_context_hash`, count them as one distinct source. This is additive, backward compatible, and within allowed files.
- Collector already has access to `model` and `hypotheses_injected` from trace context.
- No frozen surface mutation.

---

### 3.6 Counter Evidence Handling

**Attack description:**
Negative evidence against a hypothesis can disappear from the pipeline:
- `weaken_hypothesis` candidates are rejected by validator (`ctype in ("weaken", "weaken_hypothesis") → rejected`)
- `inconclusive` observations are excluded from `validation_runs` by `is_countable_observation`
- Failed traces (where the hypothesis was injected but the task failed) may not generate candidates at all (R7 only fires for `status==success` traces)
- Rejected candidates are tracked in the group but not in the observation log

The system only preserves positive evidence, creating a survivorship bias where hypotheses appear more validated than they actually are.

**Current defense:**
- `weaken`/`weaken_hypothesis` rejection is by design — these require human review
- `inconclusive` exclusion is by design — prevents weak evidence from inflating counts
- Rejected candidates are preserved in `group["candidates"]` with `_rejected=True` for audit

**Remaining weakness:**
- No negative evidence log — the system has no record of how many times a hypothesis was weakened, refuted, or inconclusive
- No counter-evidence ratio — the validator doesn't know that a hypothesis with 2 confirming observations also had 5 weakening observations
- Failed traces are silent — an agent could try to use a hypothesis, fail, and the failure is not recorded against the hypothesis
- `weaken_hypothesis` candidates are written to `memory-candidates.yaml` but rejected at validation — they are visible in the candidates file but not in the observation log or validation results

**Required invariant:**
**Negative Evidence Preservation Invariant:** Every `weaken_hypothesis`, `inconclusive`, and `refuted` observation SHALL be preserved in the observation log with full provenance. The validator SHALL report a counter-evidence ratio (confirming / total observations) in the validation result.

**Implementation impact:**
- **LOW** — Modify `collect_from_trace_ids` to also write non-countable observations to the observation log (currently they are skipped by `is_countable_observation` gate). Add a `countable: false` field to distinguish them. In `validate_memory_group`, compute `counter_evidence_ratio = confirmations / total_observations`.
- This is additive, backward compatible, and within allowed files (collector.py, validator.py).
- No frozen surface mutation.

---

### 3.7 Temporal Context Drift

**Attack description:**
A memory that was validated under a specific environment configuration (code version, dependency version, model version, tool version, task distribution) becomes actively harmful after the environment changes. For example:
- A memory recommending a specific library version becomes wrong after a major version bump
- A memory about a deprecated API becomes harmful after the API is removed
- A memory about Python 3.12 behavior becomes wrong under Python 3.14

The system has no mechanism to detect or flag temporal staleness.

**Current defense:**
- Trust Gate M6_staleness is always `pass` — it is a placeholder, not an active check
- `observation_count` grows with time, which could indicate continued relevance — but the observations themselves may be from the old environment
- `retrieval-index.yaml` has `updated_at` and `created_at` timestamps — but no mechanism to re-validate after a certain age

**Remaining weakness:**
- No environment fingerprint in observation provenance — the system doesn't know what code/dependency/model versions were active when the observation was made
- No staleness trigger — a memory that hasn't been observed in 6 months is treated the same as a memory observed yesterday
- No decay mechanism for memories that haven't been re-confirmed recently

**Required invariant:**
**Context-Bounded Validity Invariant:** A memory's validity SHALL be bounded by the environment context in which it was last confirmed. If the environment context changes (code version, dependency version, model version), the memory SHALL be flagged for re-validation.

**Implementation impact:**
- **LOW (audit) / MEDIUM (enforcement)** — Phase 8.7 should add environment context to observation log entries (e.g., `env_fingerprint: {python_version, model_family, code_version_hash}`). The auditor (validator) can surface mismatches but not reject on them. Full staleness re-evaluation is deferred to Phase 8.8+.
- Collector already has access to environment context from trace metadata.
- No frozen surface mutation for audit-only implementation.

---

### 3.8 Observation Identity Integrity

**Attack description:**
Different pipeline components use different identifiers for the same observation, creating identity fragmentation:
- **Retrieval history** uses `memory_id` + timestamp
- **Injection telemetry** uses `influence_breakdown[hid]` keyed by hypothesis ID
- **Collector** generates `candidate_id` with `CAND-{eid}-HYP-{hyp_id}` format
- **Validator** groups by `target_memory` and counts by `canonical_source`
- **Observation log** uses `source_loop` + `observed_at`
- **Promotion record** uses `memory_id` + `promoted_at`

There is no single, cross-component observation identity that can be used to trace an observation from injection through validation to promotion. This makes auditing and debugging difficult.

**Current defense:**
- Candidate ID format is explicit about execution and hypothesis provenance
- `hypothesis_engagement` carries provenance fields
- Observation log entries carry `source_loop`, `source_execution`, `candidate_type`, `same_loop_as_creation`

**Remaining weakness:**
- No single `observation_id` that spans all pipeline components
- Different components reference different aspects of the same observation
- Cross-component tracing requires manual correlation of `execution_id` + `hypothesis_id` across multiple files

**Required invariant:**
**Single Observation Identity Invariant:** Every observation of a hypothesis SHALL carry a unique, cross-component `observation_id` that is preserved from injection through collection, validation, and promotion.

**Implementation impact:**
- **LOW** — Add `observation_id` (e.g., `OBS-{execution_id}-{hypothesis_id}`) to `influence_breakdown`, candidate, observation log, and validation result. This is purely additive metadata — no counting or validation logic changes.
- Collector and runtime_adapter are allowed files. No frozen surface mutation.

---

## 4. Proposed Phase 8.7 Invariants

### 4.1 Evidence Independence Invariant

**Statement:** Two observations of the same hypothesis SHALL NOT be counted as independent if they derive from the same root task execution. Observations are independent only if they originate from different task executions with different `root_task_id` values.

**Enforcement:** `validator.py` `enrich_groups_with_observation_log` — add `root_task_id` to observation log; count distinct `root_task_id` values instead of distinct `source_loop` values for hypothesis lane.

**Priority:** P1 (must)

### 4.2 Retrieval Diversity Invariant

**Statement:** Over any rolling window of N retrievals, no single hypothesis SHALL account for more than 50% of hypothesis injections, and at least 3 distinct hypotheses SHALL be injected across the window.

**Enforcement:** `runtime_adapter.py` injection logic — track hypothesis injection frequency in a rolling window; if a hypothesis exceeds 50%, skip or downgrade its injection. Audit-only in Phase 8.7; full enforcement in Phase 8.8.

**Priority:** P2 (audit only in 8.7)

### 4.3 No Positive Feedback Promotion Invariant

**Statement:** The promotion of a hypothesis to `validated` or `runtime_validated` SHALL NOT increase its retrieval score. The retrieval score of a hypothesis SHALL be determined solely by `static_relevance` (content match) and capped at its initial value.

**Enforcement:** `validator.py` `_build_result` — for hypothesis lane, compute confidence using `min(observation_count, initial_observation_count)` to prevent confidence growth from inflating retrieval score. The `retrieval_optimizer.py` scoring is already multiplicative and caps quality bonus at 30%, so this is defense-in-depth.

**Priority:** P1 (must, but enforcement is outside frozen surface)

### 4.4 Causal Independence Invariant

**Statement:** Two observations of the same hypothesis SHALL NOT be counted as independent if they originate from the same model family AND the same retrieval context (same `hypotheses_injected` set hash). At least one of these dimensions must differ.

**Enforcement:** `validator.py` `enrich_groups_with_observation_log` — add `model_family` and `retrieval_context_hash` to observation log; if two observations share both, count them as one distinct source for hypothesis lane.

**Priority:** P1 (must)

### 4.5 Negative Evidence Preservation Invariant

**Statement:** Every `weaken_hypothesis`, `inconclusive`, and `refuted` observation SHALL be preserved in the observation log with full provenance. The validator SHALL report a counter-evidence ratio (confirming observations / total observations) in the validation result.

**Enforcement:** `collector.py` `collect_from_trace_ids` — write non-countable observations to log with `countable: false` flag. `validator.py` `_build_result` — compute `counter_evidence_ratio` from observation log.

**Priority:** P1 (must)

### 4.6 Context-Bounded Validity Invariant

**Statement:** A memory's validity SHALL be bounded by the environment context in which it was last confirmed. If the environment context changes (code version, dependency version, model version), the memory SHALL be flagged for re-validation.

**Enforcement:** `collector.py` — add `env_fingerprint` to observation log. `validator.py` `_build_result` — add `staleness_warning` if environment context has changed since last observation. Audit-only in Phase 8.7.

**Priority:** P2 (audit only in 8.7)

### 4.7 Single Observation Identity Invariant

**Statement:** Every observation of a hypothesis SHALL carry a unique, cross-component `observation_id` that is preserved from injection through collection, validation, and promotion.

**Enforcement:** `runtime_adapter.py` — generate `observation_id` (e.g., `OBS-{execution_id}-{hypothesis_id}`) in `influence_breakdown`. `collector.py` — propagate to candidate and observation log. `validator.py` — include in validation result.

**Priority:** P1 (must)

---

## 5. Frozen Surface Impact Analysis

| Surface | Would Phase 8.7 changes affect it? | Analysis |
|---------|-----------------------------------|----------|
| **`promoter.py`** | **NO** | All Phase 8.7 invariants are enforced in collector and validator. The promoter receives the same `validation-results.yaml` format with additional audit fields — no schema break. Promotion logic unchanged. |
| **`retrieval_optimizer.py`** | **NO** | The No Positive Feedback invariant (4.3) is enforced in `validator.py` by capping confidence growth, not in the retrieval optimizer. The multiplicative scoring model already caps quality bonus at 30% — the invariant is defense-in-depth. No change to scoring logic. |
| **`retrieval_adapter.py`** | **NO** | Retrieval diversity (4.2) is enforced in `runtime_adapter.py` injection logic, not in the retrieval adapter. The adapter's `adapt()` function is unchanged. |
| **`prompts/`** | **NO** | No prompt changes. The `[UNVALIDATED]` label and hypothesis injection guidance remain unchanged. |
| **`benchmark templates`** | **NO** | No template changes. The benchmark suite uses the same frozen pipeline (`build_trace → collect → validate`). |

### Files affected by Phase 8.7 (within allowed set)

| File | Changes | Invariants | Type |
|------|---------|------------|------|
| `runtime/memory-feedback/collector/collector.py` | Add `root_task_id`, `observation_id`, `env_fingerprint`, `model_family`, `retrieval_context_hash` to observation log; write non-countable observations; add `countable` flag | 4.1, 4.4, 4.5, 4.6, 4.7 | Additive |
| `runtime/memory-feedback/promotion/validator.py` | Add diversity counting (root_task_id, model_family+context_hash dedup); compute counter_evidence_ratio; cap confidence growth; add staleness_warning | 4.1, 4.3, 4.4, 4.5, 4.6 | Additive |
| `runtime/loop-controller/runtime_adapter.py` | Generate `observation_id`; add `model_family`, `retrieval_context_hash`, `root_task_id` to `influence_breakdown`; add injection diversity tracking (audit) | 4.2, 4.4, 4.7 | Additive |
| `runtime/loop-controller/tests/test_phase_8_7_integrity.py` | New test file for Phase 8.7 invariants | — | New file |

---

## 6. Phase 8.7 Scope Boundary

### IN SCOPE

| Item | Description | Priority |
|------|-------------|----------|
| **I10 — Evidence Independence** | Add `root_task_id` to observation log; count distinct `root_task_id` values for hypothesis lane (replaces `source_loop` dedup) | P1 |
| **I11 — Causal Independence** | Add `model_family` and `retrieval_context_hash` to observation log; collapse same-(model+context) observations to one source | P1 |
| **I12 — Negative Evidence Preservation** | Write non-countable observations to log with `countable: false`; compute `counter_evidence_ratio` in validator | P1 |
| **I13 — Single Observation Identity** | Generate `observation_id` in `runtime_adapter`; propagate through collector, validator, and observation log | P1 |
| **I14 — No Positive Feedback** | Cap confidence growth for hypothesis lane in `_build_result`; prevent promotion from inflating retrieval score | P1 |
| **I15 — Retrieval Diversity** | Add injection frequency tracking (audit-only); surface diversity metrics in validation result | P2 |
| **I16 — Context-Bounded Validity** | Add `env_fingerprint` to observation log; add `staleness_warning` in validation result (audit-only) | P2 |
| **Tests** | 8-10 new tests in `test_phase_8_7_integrity.py`; all 56 existing tests must stay green | P1 |

### OUT OF SCOPE

| Item | Reason | Deferred to |
|------|--------|-------------|
| Content-level fact verification | Requires external ground truth or human review | Phase 8.9+ |
| Retrieval scoring changes | `retrieval_optimizer.py` is frozen | Phase 8.9+ (after frozen surface review) |
| Promotion logic changes | `promoter.py` is frozen | Phase 8.9+ (after frozen surface review) |
| Full staleness re-evaluation engine | Requires environment fingerprint comparison and automated re-validation | Phase 8.8+ |
| Retrieval diversity enforcement (not just audit) | Requires retrieval_optimizer changes | Phase 8.8+ |
| Agent/model diversity requirements | Requires new trace fields and longer validation | Phase 8.8+ |
| Temporal separation (min_loop_interval) | Requires cross-loop timestamp comparison; spec'd in 8.6 but deferred | Phase 8.8+ |

---

## 7. Implementation Readiness Decision

### Decision: APPROVED FOR IMPLEMENTATION

**Rationale:**

1. **All Phase 8.7 invariants are additive** — no existing counting logic is removed, no Phase 8.6 invariants (I1-I9) are relaxed, no backward-incompatible schema changes.

2. **No frozen surface mutation** — all changes are confined to `collector.py`, `validator.py`, and `runtime_adapter.py` (C1 pattern). The promoter, retrieval_optimizer, retrieval_adapter, prompts, and benchmark templates are untouched.

3. **Existing test suite (56 tests) is the regression baseline** — all Phase 8.7 changes must pass the same 56 tests that Phase 8.6 passed. New tests are additive.

4. **P1 invariants (I10-I14) are low-risk, high-value** — they add provenance metadata and audit fields without changing the counting model. The most impactful change (I10 evidence independence) is a straightforward dedup dimension addition.

5. **P2 invariants (I15-I16) are audit-only** — they add metadata and warnings without enforcement, providing value without risk.

6. **Phase 8.6 closure is confirmed** — C1-C5 all PASS, 56/56 tests green, Runtime Closure PASS. Phase 8.7 builds on stable ground.

**Constraints during implementation:**

- Do NOT modify `promoter.py`, `retrieval_optimizer.py`, `retrieval_adapter.py`, prompts, or benchmark templates
- Do NOT remove or weaken any Phase 8.6 invariant (I1-I9)
- Do NOT change the counting model for established lane (R1-R6)
- All new fields default safely (`""`, `false`, `None`) for backward compatibility
- 56 existing tests must stay green

---

**Phase 8.7 Architecture Review complete. Ready for implementation planning.**