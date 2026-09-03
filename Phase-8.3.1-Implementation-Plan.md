# Phase 8.3.1 — Hypothesis Feedback Closure Implementation Plan

**Date:** 2026-09-03
**Status:** PENDING REVIEW
**Author:** Agent OS Release Hardening Engineer

---

## 1. Problem Statement

Phase 8.3 Runtime Validation proved cross-loop retrieval works (H-467 ranked #1 in Run 2, injected into agent prompt, agent recognized and validated it). But the Validation/Promotion closure failed because:

**The collector generates candidates only from technical patterns (file:line, pattern → P8-*), never from injected hypotheses.** It has no awareness of which hypotheses the agent just used. So H-467 never gets a `target_memory=H-467` candidate, and the validator never accumulates a second observation.

---

## 2. Data Flow Analysis

### 2.1 Current (broken) path

```
retrieval → hypothesis injection → agent response
    ↓
trace file:
  memory_retrieval:
    memories_considered: [...]
    influence_breakdown:
      H-467: {referenced: true, engagement_level: "hypothesis_confirmed", ...}
    decision_influence:
      provenance:
        - {memory_id: H-467, memory_type: hypothesis, agent_reference: semantic}
    ↓
collector.generate_candidates()  ← NEVER reads influence_breakdown or provenance
    ↓
candidates: [target_memory=P8-xxx, ...]  ← NO H-467 candidate
    ↓
validator: sees only 1 observation for H-467 → hypothesis (not validated)
```

### 2.2 Target (fixed) path

```
trace file:
  memory_retrieval:
    influence_breakdown:
      H-467: {referenced: true, engagement_level: "hypothesis_confirmed"}
    ↓
collector.generate_candidates()  ← NEW: reads influence_breakdown + provenance
    ↓
candidates:
  - target_memory=P8-xxx (existing pattern lane)
  - target_memory=H-467, candidate_type=reinforce_hypothesis  (NEW lane)
    ↓
validator: H-467 has 2 observations → validated
```

---

## 3. Source of Truth for Hypothesis Engagement

The trace file already contains everything needed:

```yaml
# In trace EXEC-*.yaml:
memory_retrieval:
  influence_breakdown:
    H-467-STATESTORE-WRITE-----REDIS----:
      type: hypothesis
      influence: hypothesis_confirmed
      memory_id: H-467-STATESTORE-WRITE-----REDIS----
      retrieval_score: 0.307
      referenced: true
      id_mentioned: false
      term_matches: 5
      changed_decision: false
  decision_influence:
    level: hypothesis_confirmed
    provenance:
      - memory_id: H-467-STATESTORE-WRITE-----REDIS----
        memory_type: hypothesis
        injection_format: hypothesis_injection
        agent_reference: semantic
```

**Key fields:**
- `referenced: true` → agent engaged with this hypothesis
- `engagement_level: hypothesis_confirmed` → agent confirmed it
- `term_matches: N` → degree of semantic match
- `provenance[].agent_reference: semantic` → how agent referenced it

**No string-guessing needed.** The `_detect_hypothesis_engagement()` function in `runtime_adapter.py` already computes these fields. The trace writer already stores them.

---

## 4. Implementation Plan

### 4.1 Modified Files

| File | Change | Purpose |
|---|---|---|
| `runtime/memory-feedback/collector/collector.py` | ~30 lines | Add R7 rule to `generate_candidates()`: read `influence_breakdown` from trace, produce `reinforce_hypothesis` candidates |
| `runtime/memory-feedback/collector/team_result_collector.py` | ~25 lines | Add hypothesis lane to `generate_candidates()`: read `hypotheses_injected` from source, produce `reinforce_hypothesis` candidates for engaged hypotheses |
| `runtime/loop-controller/loop_controller.py` | ~5 lines | Pass `hypotheses_injected` metadata to team_result_collector path |
| `runtime/loop-controller/validation/team-result-*.yaml` | metadata-only | Add `hypotheses_injected` field in team-result output |

### 4.2 New Rule: R7 — Hypothesis Observation

```python
# R7: hypothesis engagement → reinforce_hypothesis candidate
# For each hypothesis in influence_breakdown that the agent referenced:
for hyp_id, eng in influence_breakdown.items():
    if eng.get("referenced") and eng.get("engagement_level") in (
        "hypothesis_used", "hypothesis_confirmed", "hypothesis_changed_decision"
    ):
        candidates.append(make_candidate(
            cid=f"CAND-{eid}-{hyp_id}",
            target_mem=hyp_id,         # ← Directly targets the hypothesis
            ctype="reinforce_hypothesis",
            outcome="confirmed" if eng.get("engagement_level") == "hypothesis_confirmed" else "observed",
            reasoning=f"Agent engaged with hypothesis {hyp_id} (level={eng['engagement_level']}, "
                      f"term_matches={eng.get('term_matches', 0)}). "
                      f"This is observation #{observation_count} for this hypothesis.",
        ))
```

### 4.3 Data Source (trace-based collector)

```python
# In collector.py generate_candidates():
influence_breakdown = mem_retrieval.get("influence_breakdown", {})

# R7: Hypothesis observation
for hyp_id, eng in influence_breakdown.items():
    if hyp_id in mem_used:  # Already handled by R1, skip
        continue
    if not eng.get("referenced"):
        continue
    level = eng.get("engagement_level", "none")
    if level in ("hypothesis_used", "hypothesis_confirmed", "hypothesis_changed_decision"):
        reason = (
            f"Hypothesis {hyp_id} was engaged by agent "
            f"(level={level}, term_matches={eng.get('term_matches', 0)}). "
            f"Evidence from execution {eid}."
        )
        candidates.append(make_candidate(
            cid=f"CAND-{eid}-{hyp_id}",
            target_mem=hyp_id,
            ctype="reinforce_hypothesis",
            outcome="confirmed" if level == "hypothesis_confirmed" else "observed",
            reasoning=reason,
        ))
```

### 4.4 Data Source (team-result collector)

The `team_result_collector.py` generates candidates from `team-result-*.yaml` files. Currently it receives `source` (the TeamResult dict) via `generate_candidates(experiences, source)`. The source dict has `loop_id`, `team_id`, `team_result`, etc.

**New field needed in team-result YAML:**

```yaml
# team-result-LOOP-*.yaml (new field)
hypotheses_injected:
  - H-467-STATESTORE-WRITE-----REDIS----
  - H-023-INTERVIEWSTATESTORE-JAVA-37-44
  - H-024-INTERVIEWSTATESTORE-JAVA-48-51
  - H-025-INTERVIEWSTATESTORE-JAVA-36-38
  - H-027-INTERVIEWSTATESTORE-JAVA-34-39
hypothesis_engagement:
  H-467-STATESTORE-WRITE-----REDIS----:
    referenced: true
    engagement_level: hypothesis_confirmed
    term_matches: 5
```

The `hypothesis_engagement` can be computed from the agent output text using the same `_detect_hypothesis_engagement()` function already in `runtime_adapter.py`.

**Where to populate `hypotheses_injected`:** In `loop_controller.py`, when writing the team-result file, the loop state already has `state["retrieval"]["hypotheses"]` (the list of injected hypothesis IDs). This can be written into the team-result.

### 4.5 Trust Boundary Preservation

```
hypothesis → reinforce_hypothesis candidate → validator observation +1
    ↓ (if observation_count >= 2)
validated hypothesis → promotion → established memory
```

**No shortcuts.** The `reinforce_hypothesis` candidate type is distinct from `reinforce` (which targets established memories). The validator already handles this correctly:
- `target_memory=H-*` with `candidate_type=reinforce_hypothesis` → increment observation count
- Observation count reaches threshold → status changes to `validated`
- Validated hypothesis → eligible for promotion

---

## 5. Architecture Impact

```
BEFORE:
  collector.generate_candidates(trace)
    ├── R1: reinforce  (established memory)
    ├── R2: AP-001
    ├── R3: weaken     (established memory)
    ├── R4: weaken     (no influence)
    ├── R5: create_hypothesis
    └── R6: reinforce  (risk)

AFTER:
  collector.generate_candidates(trace)
    ├── R1: reinforce  (established memory)
    ├── R2: AP-001
    ├── R3: weaken     (established memory)
    ├── R4: weaken     (no influence)
    ├── R5: create_hypothesis
    ├── R6: reinforce  (risk)
    └── R7: reinforce_hypothesis (hypothesis engagement)  ← NEW
```

**Parallel lane, not a replacement.** The existing R1-R6 rules are unchanged. R7 is additive.

### 5.1 For team-result collector

```
BEFORE:
  team_result_collector.generate_candidates(experiences, source)
    ├── R1: reinforce  (multi-agent pattern)
    ├── R2: create_hypothesis (high confidence)
    └── R3: weaken     (failed agents)

AFTER:
  team_result_collector.generate_candidates(experiences, source)
    ├── R1: reinforce  (multi-agent pattern)
    ├── R2: create_hypothesis (high confidence)
    ├── R3: weaken     (failed agents)
    └── R4: reinforce_hypothesis (hypothesis engagement)  ← NEW
```

---

## 6. Frozen Surface Check

| Surface | Impact | Risk |
|---|---|---|
| **Memory schema** | None — `reinforce_hypothesis` candidates target existing H-* memory IDs | None |
| **Benchmark** | None — no scoring changes | None |
| **Scoring rubric** | None — `final_score` formula unchanged | None |
| **Agent prompt** | None — no prompt changes | None |
| **Retrieval** | None — two-pass retrieval unchanged | None |
| **Validator** | None — `reinforce_hypothesis` is a new `candidate_type` but validator groups by `target_memory`, which already handles H-* IDs | Low |
| **Promoter** | None — promoter already handles H-* memory IDs | None |
| **Existing R1-R6 rules** | None — additive only | None |
| **Trust boundary** | None — hypothesis → validated → established workflow unchanged | None |

---

## 7. Data Flow Change Summary

```
┌─────────────────────────────────────────────────────────────┐
│                  EXISTING (UNCHANGED)                        │
│                                                             │
│  Agent Output                                                │
│      ↓                                                      │
│  experience_extractor → technical_patterns                   │
│      ↓                                                      │
│  team_result_collector → R1/R2/R3 → P8-* candidates         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                  NEW (HYPOTHESIS FEEDBACK LANE)              │
│                                                             │
│  Trace: influence_breakdown                                  │
│      ↓                                                      │
│  collector.generate_candidates() → R7                        │
│      ↓                                                      │
│  reinforce_hypothesis candidates → H-* targets               │
│                                                             │
│  TeamResult: hypotheses_injected + agent_output               │
│      ↓                                                      │
│  _detect_hypothesis_engagement(agent_output, hypotheses)     │
│      ↓                                                      │
│  team_result_collector → R4 → reinforce_hypothesis candidates│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Implementation Steps

### Step 1: Trace-based collector — R7 rule
- In `collector.py` `generate_candidates()`, read `influence_breakdown` from `mem_retrieval`
- For each hypothesis with `referenced=true` and engagement level >= `hypothesis_used`, create `reinforce_hypothesis` candidate
- `target_memory` = hypothesis ID (e.g., `H-467-STATESTORE-WRITE-----REDIS----`)

### Step 2: Loop controller — pass hypotheses to team-result
- In `loop_controller.py`, when writing team-result, include `state["retrieval"]["hypotheses"]` as `hypotheses_injected`

### Step 3: Team-result collector — hypothesis lane
- In `team_result_collector.py` `generate_candidates()`, read `hypotheses_injected` from source
- Use `_detect_hypothesis_engagement()` against lead agent output text
- Create `reinforce_hypothesis` candidates for engaged hypotheses

### Step 4: Tests
- `test_hypothesis_feedback_candidate_trace`: mock trace with influence_breakdown → verify R7 produces `reinforce_hypothesis`
- `test_hypothesis_feedback_candidate_team_result`: mock team-result with hypotheses_injected → verify candidate produced
- `test_unreferenced_hypothesis_no_candidate`: hypothesis in trace but not referenced → no candidate
- `test_hypothesis_candidate_flows_to_validator`: full pipeline: candidate → validator observes it

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `influence_breakdown` key format mismatch between trace and collector | Low | Both use the same `memory_id` string from `retrieval_optimizer` |
| Team-result output doesn't have agent response text for hypothesis detection | Low | Lead agent output is already in `team_result.lead_output.output` |
| `_detect_hypothesis_engagement()` not importable in team_result_collector | Low | Add `sys.path.insert` or move function to shared module |
| Duplicate candidates if hypothesis is both in `memories_used` and `influence_breakdown` | Low | R7 skips if `hyp_id in mem_used` (already handled by R1) |
| False positive engagement detection | Low | `_detect_hypothesis_engagement()` already validated in Phase 8.2.1.5 tests |

---

## 10. File Summary

| File | Lines | Change Type |
|---|---|---|
| `collector.py` | +20 | Add R7 rule |
| `team_result_collector.py` | +25 | Add hypothesis lane |
| `loop_controller.py` | +5 | Pass hypotheses_injected to team-result |
| `test_phase_8_3_1_hypothesis_feedback.py` | NEW ~200 | 4 test cases |

**Total: ~50 lines production, ~200 lines test.**

---

**Awaiting review before implementation.**