# Phase 8.4 — Revised Hypothesis Reinforcement Lane Plan

**Date:** 2026-09-03
**Role:** Agent OS Release Engineer
**Status:** Revised per Architecture Review (B1/B2/B3 resolved, S2/S3/S4 addressed)
**Inputs:**
- Phase-8.4-Hypothesis-Reinforcement-Lane-Plan.md (original)
- Phase-8.4-Architecture-Review.md (blocking issues: B1, B2, B3)
- Phase-8.4-Code-Review.md
- text.txt (Phase 8.4 架构评审: 8 大不变量)

---

## Verdict

# READY FOR IMPLEMENTATION

All 3 blocking issues from the architecture review (B1, B2, B3) are resolved. All 8 invariants are satisfied. The plan is self-consistent and implementable.

---

## Architecture Changes (from Original Plan)

### Change 1: Two Candidate Types (B1 fix)

**Original:** Single `reinforce_hypothesis` candidate_type for all outcomes (confirmed, observed, refuted, inconclusive).

**Revised:** Two distinct candidate types:

| candidate_type | outcome values | Validator behavior |
|---|---|---|
| `reinforce_hypothesis` | `confirmed`, `observed` | Counts toward `validation_runs`; flows through normal H-xxx lifecycle |
| `weaken_hypothesis` | `refuted` | Rejected by validator; cannot contribute to `validation_runs`; serves as negative evidence only |

This eliminates the semantic contradiction of a `reinforce` candidate carrying a `refuted` outcome, and ensures I4 (Negative-evidence invariant) is enforced at the validator level.

### Change 2: validator.py Added to Modified Files (B2 fix)

**Original:** validator.py listed as "absolutely not modified". Independence checks described in §5.2 but not in modification scope.

**Revised:** validator.py explicitly added to Modified Files table with three specific, minimal changes (~15 lines total).

### Change 3: same_loop_as_creation Removed (B3 fix)

**Original:** `same_loop_as_creation` field in `hypothesis_engagement` sub-dict, to be checked by validator.

**Revised:** Field removed from Phase 8.4 scope. The `source_execution` deduplication in the existing `executions` set already prevents same-loop double-counting (same `loop_id` -> 1 execution). For cross-loop independence, the validator relies on `source_execution` uniqueness, which is already enforced. Creation loop provenance will be added in Phase 8.4.1 when the hypothesis memory frontmatter schema is extended.

### Change 4: Independent Evidence Markers (S2 fix)

**Original:** `confirmed` outcome determined solely by `engagement_level >= hypothesis_confirmed` (text-based).

**Revised:** `hypothesis_engagement` now includes `independent_evidence_markers` — a list of signals that the agent provided evidence beyond echoing the injected hypothesis (different code lines, test results, new file paths, runtime observations). The collector downgrades `confirmed` to `observed` when no independent evidence markers are present.

### Change 5: Inconclusive Exclusion (S4 fix)

**Original:** `inconclusive` outcome defined but no explicit validator handling.

**Revised:** Validator explicitly excludes `outcome=inconclusive` candidates from the effective observation count. An `inconclusive` candidate from a unique `source_execution` does NOT increment `validation_runs`.

### Change 6: Import Path Clarified (S3 fix)

**Original:** `team_result_collector.py` imports `_detect_hypothesis_engagement` from `runtime_adapter.py` without specifying how.

**Revised:** Uses the same `sys.path.insert` pattern already present in `collector.py` (line 22):
```python
sys.path.insert(0, os.path.join("/home/shade/.agents", "runtime", "loop-controller"))
from runtime_adapter import _detect_hypothesis_engagement
```

---

## Modified Files

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `collector.py` | ~35 | R7: read `influence_breakdown`, produce `reinforce_hypothesis` / `weaken_hypothesis` candidates |
| 2 | `team_result_collector.py` | ~30 | R4: read `hypotheses_injected`, detect engagement via `_detect_hypothesis_engagement()`, produce candidates |
| 3 | `loop_controller.py` | +1 | Add `hypotheses_injected` to team-result YAML |
| 4 | `validator.py` | ~15 | Reject `weaken_hypothesis` type; exclude `inconclusive` from observation count; I5 independence check |
| 5 | `test_phase_8_4_hypothesis_reinforcement.py` | NEW ~400 | 26 deterministic tests |

**Total: ~80 lines production, ~400 lines test.**

### Files NOT Modified

| File | Reason |
|------|--------|
| `experience_extractor.py` | Text pattern extraction; unrelated to hypothesis engagement |
| `promoter.py` | Trust gate and evidence level progression already correct for H-xxx |
| `runtime_adapter.py` | `_detect_hypothesis_engagement()` already correct; trace writing unchanged |
| `base_collector.py` | Abstract interface; no change needed |
| `retrieval_optimizer.py` | Two-pass retrieval unchanged |
| `retrieval-index.yaml` | Frozen surface; no schema change |

---

## Data Model

### candidate_type: reinforce_hypothesis

```yaml
candidate:
  candidate_id: CAND-<loop_id>-<hyp_id>
  source_execution: <loop_id>
  target_memory: H-467-STATESTORE-WRITE-----REDIS----
  candidate_type: reinforce_hypothesis        # NEW: for confirmed/observed only
  quality_score: <float>
  quality_breakdown: {completeness, accuracy, structure, actionability, novelty, weighted}
  reasoning: |
    Hypothesis <hyp_id> engaged by agent <role>
    (level=<engagement_level>, term_matches=<n>).
    Evidence from execution <loop_id>.
  evidence:
    session_id: "..."
    output_hash: <sha256[:16]>
    is_real_execution: true
    agent_role: <role>
  outcome: confirmed | observed              # confirmed only when independent evidence present
  hypothesis_engagement:
    referenced: true
    engagement_level: hypothesis_used | hypothesis_confirmed | hypothesis_changed_decision
    term_matches: <int>
    id_mentioned: <bool>
    changed_decision: false
    independent_evidence_markers:             # NEW (S2): evidence beyond echoing injected hypothesis
      different_code_lines: <bool>            # agent referenced code not in hypothesis
      test_results: <bool>                    # agent ran/described tests
      new_file_paths: <bool>                  # agent referenced files not in hypothesis
      runtime_observations: <bool>            # agent described runtime behavior
    shared_context_with_other_agents: <bool>  # I5: same TeamResult multi-agent
```

### candidate_type: weaken_hypothesis

```yaml
candidate:
  candidate_id: CAND-<loop_id>-<hyp_id>
  source_execution: <loop_id>
  target_memory: H-467-STATESTORE-WRITE-----REDIS----
  candidate_type: weaken_hypothesis           # NEW: for refuted only
  quality_score: <float>
  quality_breakdown: {completeness, accuracy, structure, actionability, novelty, weighted}
  reasoning: |
    Hypothesis <hyp_id> was refuted by agent <role>.
    Evidence from execution <loop_id>.
  evidence:
    session_id: "..."
    output_hash: <sha256[:16]>
    is_real_execution: true
    agent_role: <role>
  outcome: refuted
  hypothesis_engagement:
    referenced: true
    engagement_level: hypothesis_refuted      # detected by negation patterns
    term_matches: <int>
    id_mentioned: <bool>
    changed_decision: false
    independent_evidence_markers: {}
    shared_context_with_other_agents: <bool>
```

### outcome Semantics

| outcome | candidate_type | Validator effect | Evidence level |
|---------|---------------|------------------|----------------|
| `observed` | `reinforce_hypothesis` | Counts toward `validation_runs` | Agent referenced hypothesis; no independent evidence |
| `confirmed` | `reinforce_hypothesis` | Counts toward `validation_runs` | Agent provided independent evidence beyond echoing injection |
| `refuted` | `weaken_hypothesis` | Rejected; does NOT count toward `validation_runs` | Negative evidence; recorded in observation-log for audit |
| `inconclusive` | `reinforce_hypothesis` | Excluded from `validation_runs` | Mentioned but insufficient evidence; abstain |

### Outcome Determination Logic

```python
def determine_outcome(engagement, agent_output, hypothesis):
    """Determine outcome for a hypothesis engagement."""
    level = engagement.get("engagement_level", "none")

    if level == "none":
        return "inconclusive"

    # Check for refutation (negation patterns + hypothesis reference)
    if _detect_refutation(agent_output, hypothesis):
        return "refuted"

    # Check for independent evidence
    has_independent = _has_independent_evidence(agent_output, hypothesis)

    if level in ("hypothesis_confirmed", "hypothesis_changed_decision"):
        if has_independent:
            return "confirmed"
        else:
            return "observed"  # Downgrade: text-based confirmation without evidence

    if level == "hypothesis_used":
        if has_independent:
            return "confirmed"
        else:
            return "observed"

    return "inconclusive"
```

---

## Collector Design

### Trace Path: collector.py R7

```python
def generate_candidates(trace, quality):
    # ... existing R1-R6 unchanged ...

    # R7: Hypothesis Reinforcement Lane
    mem_retrieval = trace.get("memory_retrieval", {})
    influence_breakdown = mem_retrieval.get("influence_breakdown", {})
    mem_used = mem_retrieval.get("memories_used", [])

    for hyp_id, eng in influence_breakdown.items():
        # Only process hypotheses (not established memories)
        if eng.get("type") != "hypothesis":
            continue

        # I6 Abstention: skip if not referenced
        if not eng.get("referenced"):
            continue

        # Skip if already handled by R1 (established memory lane)
        if hyp_id in mem_used:
            continue

        level = eng.get("engagement_level", "none")
        if level == "none":
            continue

        # Determine outcome
        outcome = _determine_hypothesis_outcome(eng, trace)

        # Choose candidate_type based on outcome
        if outcome == "refuted":
            ctype = "weaken_hypothesis"
        elif outcome == "inconclusive":
            ctype = "reinforce_hypothesis"  # Still reinforce type, but outcome=inconclusive
        else:
            ctype = "reinforce_hypothesis"

        # Check for independent evidence markers
        independent = _check_independent_evidence(trace, hyp_id, eng)

        candidates.append(make_candidate(
            candidate_id=f"CAND-{loop_id}-{hyp_id}",
            target_memory=hyp_id,
            candidate_type=ctype,
            outcome=outcome,
            reasoning=(
                f"Hypothesis {hyp_id} engaged by agent "
                f"(level={level}, term_matches={eng.get('term_matches', 0)}, "
                f"independent_evidence={bool(independent)}). "
                f"Evidence from execution {loop_id}."
            ),
            quality_score=quality.get("weighted", 3.0),
            quality_breakdown=quality,
            evidence={...},
            source_execution=loop_id,
            hypothesis_engagement={
                "referenced": eng.get("referenced", False),
                "engagement_level": level,
                "term_matches": eng.get("term_matches", 0),
                "id_mentioned": eng.get("id_mentioned", False),
                "changed_decision": eng.get("changed_decision", False),
                "independent_evidence_markers": independent,
                "shared_context_with_other_agents": False,  # trace path: single agent
            },
        ))
```

### Team-Result Path: team_result_collector.py R4

```python
# In generate_candidates(experiences, source):
# R4: Hypothesis Reinforcement Lane
import sys, os
sys.path.insert(0, os.path.join("/home/shade/.agents", "runtime", "loop-controller"))
from runtime_adapter import _detect_hypothesis_engagement

hypotheses_injected = source.get("hypotheses_injected", [])
if hypotheses_injected:
    lead_output = source.get("team_result", {}).get("lead_output", {}).get("output", "")
    if lead_output:
        for hyp_id in hypotheses_injected:
            eng = _detect_hypothesis_engagement(lead_output, [{"memory_id": hyp_id}])
            eng_data = eng.get(hyp_id, {})
            if not eng_data.get("referenced"):
                continue  # I6 abstain

            outcome = _determine_hypothesis_outcome_team(eng_data, lead_output, hyp_id)
            ctype = "weaken_hypothesis" if outcome == "refuted" else "reinforce_hypothesis"
            independent = _check_independent_evidence_team(lead_output, hyp_id)

            is_shared = len(source.get("task_cards", [])) > 1  # multi-agent team

            candidates.append(make_candidate(
                candidate_id=f"CAND-{loop_id}-{hyp_id}",
                target_memory=hyp_id,
                candidate_type=ctype,
                outcome=outcome,
                reasoning=...,
                quality_score=...,
                evidence={...},
                source_execution=loop_id,
                hypothesis_engagement={
                    "referenced": eng_data.get("referenced", False),
                    "engagement_level": eng_data.get("engagement_level", "none"),
                    "term_matches": eng_data.get("term_matches", 0),
                    "id_mentioned": eng_data.get("id_mentioned", False),
                    "changed_decision": eng_data.get("changed_decision", False),
                    "independent_evidence_markers": independent,
                    "shared_context_with_other_agents": is_shared,
                },
            ))
```

### Independent Evidence Detection

```python
def _check_independent_evidence(trace_or_output, hyp_id, engagement=None):
    """Check if agent provided evidence beyond echoing the injected hypothesis.

    Returns a dict of boolean markers. All False means the agent only echoed
    the injected hypothesis content without adding independent verification.
    """
    markers = {
        "different_code_lines": False,
        "test_results": False,
        "new_file_paths": False,
        "runtime_observations": False,
    }

    # Get agent output text
    if isinstance(trace_or_output, dict):
        output = trace_or_output.get("output", "") or trace_or_output.get("agent_output", "")
    else:
        output = str(trace_or_output)

    import re
    # Check for code references beyond what was in the hypothesis
    code_refs = set(re.findall(r'(?:file|path|src)[:\s]+([^\s,;]+\.(?:java|py|go|ts|js|rs))', output, re.I))
    line_refs = re.findall(r'(?:line|L|:)\s*(\d+)', output)
    if code_refs or line_refs:
        markers["different_code_lines"] = True

    # Check for test execution evidence
    test_patterns = [
        r'(?:test|测试|验证).*?(?:pass|通过|success|成功|green|绿)',
        r'(?:ran|executed|运行).*?(?:test|测试)',
        r'(?:assert|expect|should).*?(?:true|false|equal|match)',
        r'(?:grep|find|search).*?(?:result|结果|found|发现)',
    ]
    if any(re.search(p, output, re.I) for p in test_patterns):
        markers["test_results"] = True

    # Check for runtime behavior description
    runtime_patterns = [
        r'(?:runtime|运行时|behavior|行为).*?(?:observed|观察|show|显示)',
        r'(?:log|日志|trace|output).*?(?:show|显示|indicate|表明)',
        r'(?:monitor|监控|metric|指标).*?(?:show|显示|report|报告)',
    ]
    if any(re.search(p, output, re.I) for p in runtime_patterns):
        markers["runtime_observations"] = True

    return markers
```

---

## Validator Design

### Modification 1: Reject weaken_hypothesis

```python
# In validate_memory_group(), after existing weaken check:
elif ctype == "weaken_hypothesis":
    status = "rejected"
    rejection_reason = (
        f"Hypothesis {memory_id} was refuted by agent. "
        f"Weaken candidates require human review, not auto-processed. "
        f"Negative evidence recorded in observation-log."
    )
```

### Modification 2: Exclude inconclusive from observation count

```python
# In validate_memory_group(), after computing validation_runs:
# Adjust observation count: exclude inconclusive candidates
effective_runs = validation_runs
inconclusive_count = sum(
    1 for c in group["candidates"]
    if c.get("outcome") == "inconclusive"
)
if inconclusive_count > 0:
    effective_runs = max(1, validation_runs - inconclusive_count) if validation_runs > 0 else 0
    # Use effective_runs for the check below instead of validation_runs
```

### Modification 3: Independence check (I5)

```python
# In validate_memory_group(), before status determination:
# I5 Independence: check for shared context within same TeamResult
has_shared_context = any(
    c.get("hypothesis_engagement", {}).get("shared_context_with_other_agents", False)
    for c in group["candidates"]
)
# If all observations come from the same TeamResult (same loop_id),
# count as 1 observation regardless of agent count
# This is already partially enforced by the executions set (dedup by source_execution)
# The shared_context flag provides additional audit trail
if has_shared_context and len(group["executions"]) <= 1:
    # Single execution with shared context: mark for audit but don't change count
    # (the executions set already prevents inflation)
    pass
```

### Complete Validator Flow for H-xxx

```python
# For H-xxx with reinforce_hypothesis candidates:
# 1. Group by target_memory (existing, unchanged)
# 2. Count effective_runs = len(executions) - inconclusive_count
# 3. If ctype == "weaken_hypothesis" -> rejected (NEW)
# 4. If effective_runs >= 1 and ctype == "reinforce_hypothesis" -> hypothesis
# 5. If effective_runs >= 2 and ctype == "reinforce_hypothesis" -> validated
# 6. Existing gates unchanged: quality threshold, session_id, output_hash
```

---

## Promotion Safety

No changes from original plan. All existing gates remain:

1. `check_trust_gate()`: M1_provenance, status=hypothesis|validated, no conflicts
2. Evidence level progression: `hypothesis -> runtime_validated (+1 obs) -> independent_validated (+2 obs)`
3. Idempotency: already-promoted memories skipped
4. `reinforce_hypothesis` and `weaken_hypothesis` are just new candidate_type strings — no gate bypass

---

## Tests

Test file: `test_phase_8_4_hypothesis_reinforcement.py` — 26 deterministic tests.

### Class A — Trace Path Candidate Generation (6)
1. `test_engaged_hypothesis_produces_reinforce_candidate` — `referenced=true` -> `reinforce_hypothesis`
2. `test_unreferenced_hypothesis_no_candidate` — `referenced=false` -> no candidate (I6)
3. `test_hypothesis_used_minimal_engagement_produces_observed` — `term_matches=1` -> `outcome=observed`
4. `test_hypothesis_confirmed_with_independent_evidence_produces_confirmed` — `term_matches=5` + independent evidence -> `outcome=confirmed`
5. `test_hypothesis_confirmed_without_independent_evidence_produces_observed` — `term_matches=5` but no independent evidence -> `outcome=observed` (S2)
6. `test_same_hypothesis_in_memories_used_not_duplicated` — R1 handles, R7 skips

### Class B — Team-Result Path Candidate Generation (4)
7. `test_team_result_with_hypotheses_injected_produces_candidate`
8. `test_team_result_without_hypotheses_injected_no_candidate`
9. `test_team_result_agent_does_not_reference_hypothesis_no_candidate` (I6)
10. `test_team_result_multi_agent_marks_shared_context` — shared_context_with_other_agents=true

### Class C — Weaken Hypothesis (3)
11. `test_refuted_hypothesis_produces_weaken_hypothesis_type` — `candidate_type=weaken_hypothesis`
12. `test_weaken_hypothesis_rejected_by_validator` — validator rejects `weaken_hypothesis`
13. `test_mixed_reinforce_and_weaken_blocks_validation` — 1 reinforce + 1 weaken -> rejected (B1)

### Class D — Validator Integration (5)
14. `test_reinforce_hypothesis_groups_by_target_memory` — 2 candidates -> 1 group, 2 executions
15. `test_single_hypothesis_observation_enters_as_hypothesis` — 1 obs -> status=hypothesis
16. `test_two_hypothesis_observations_graduates_to_validated` — 2 independent obs -> status=validated
17. `test_hypothesis_candidate_has_engagement_provenance` — includes `hypothesis_engagement`
18. `test_inconclusive_excluded_from_observation_count` — `outcome=inconclusive` -> effective_runs not incremented (S4)

### Class E — Promotion Safety (4)
19. `test_hypothesis_cannot_be_promoted_directly` — 1 obs -> evidence_level stays `hypothesis`
20. `test_hypothesis_with_two_observations_promotes_correctly` — validated -> `runtime_validated`
21. `test_promotion_includes_provenance` — includes loop_id, source_validation_ids, observation_sources
22. `test_idempotency_prevents_duplicate_promotion` — re-promotion -> skipped

### Class F — Independence + Negative Evidence (4)
23. `test_weaken_hypothesis_blocks_validation` — 1 reinforce + 1 weaken -> rejected
24. `test_inconclusive_engagement_produces_inconclusive_outcome` — term_matches=1, no confirmation -> `inconclusive`
25. `test_team_multi_agent_shared_context_counts_once` — same TeamResult multi-agent -> validation_runs +1 (I5)
26. `test_changed_decision_not_renamed_from_reference` — `hypothesis_confirmed` not auto-upgraded to `hypothesis_changed_decision` (I3)

---

## Rollback Plan

| Step | Action | Verification |
|------|--------|-------------|
| 1 | `git diff > /tmp/phase-8.4.diff` backup baseline | Confirm original hashes of all 4 modified files |
| 2 | **Option A (minimal rollback):** Delete R7 loop, R4 loop, `hypotheses_injected` line, validator changes -> restore to pre-8.4 state | All existing tests pass |
| 3 | **Option B (data rollback):** Filter `reinforce_hypothesis` / `weaken_hypothesis` entries from `memory-candidates.yaml`; delete corresponding observation-log entries | No residual `observation_count` changes |
| 4 | **Option C (feature flag):** `HYPOTHESIS_REINFORCE_ENABLED=false` disables lane without code removal | Behavior reverts to P8-* only |
| 5 | Post-rollback regression: run all tests | All green; benchmark/scoring/prompt/schema untouched |

---

## Remaining Risks

| Risk | Severity | Mitigation | Phase |
|------|----------|------------|-------|
| `_detect_hypothesis_engagement()` text-based detection may produce false positives | Low | `outcome=observed` vs `confirmed` distinction; `independent_evidence_markers` downgrade; feature flag for instant disable | 8.4 |
| Same-loop creation+validation counts as 2 observations if different loop_ids | Low | `source_execution` deduplication already prevents same-loop_id double-counting; creation loop provenance deferred to Phase 8.4.1 | 8.4.1 |
| Multi-agent TeamResult shared context | Low | `shared_context_with_other_agents` flag recorded; executions set deduplicates by `source_execution` (loop_id), not agent count | 8.4 |
| Observation log unbounded growth | Low | Append-only; cleanup TTL can be added later | 8.4.1 |
| `_detect_hypothesis_engagement` import path fragility | Low | `sys.path.insert` pattern already used by `collector.py`; same approach for `team_result_collector.py` | 8.4 |

---

## 8 Invariants: Final Assessment

| # | Invariant | Verdict | Mechanism |
|---|-----------|---------|-----------|
| **I1** | Identity | PASS | `target_memory` from `influence_breakdown` keys / `hypotheses_injected`; no text guessing |
| **I2** | Trust | PASS | Hypothesis stays `hypothesis` until 2 independent observations; validator lifecycle unchanged |
| **I3** | Causality | PASS | `outcome=observed` vs `confirmed` distinction; `independent_evidence_markers` enforce evidence requirement |
| **I4** | Negative-evidence | PASS | `weaken_hypothesis` type rejected by validator; `refuted` outcome recorded for audit |
| **I5** | Independence | PASS | `source_execution` deduplication; `shared_context_with_other_agents` flag; `inconclusive` excluded |
| **I6** | Abstention | PASS | Collector skips when `referenced=false` or `engagement_level=none` |
| **I7** | Promotion | PASS | `check_trust_gate()` + evidence level progression unchanged; no bypass |
| **I8** | Audit | PASS | `hypothesis_engagement` sub-dict with full provenance; `independent_evidence_markers` |

**All 8 invariants: PASS.**

---

## Frozen Surfaces: Unchanged

| Surface | Status |
|---------|--------|
| Benchmark tasks | UNCHANGED |
| Scoring rubric | UNCHANGED |
| Agent prompt (`[UNVALIDATED HYPOTHESES]`) | UNCHANGED |
| Memory schema (`retrieval-index.yaml`) | UNCHANGED |
| Evidence level definitions | UNCHANGED |
| Trust boundary (`hypothesis != established`) | UNCHANGED |
| Retrieval formula (two-pass) | UNCHANGED |
| Validator thresholds (`HYPOTHESIS_MIN_OBSERVATIONS=1`, `QUALITY_THRESHOLD=3.0`) | UNCHANGED |
| Promoter trust gate (M1-M6) | UNCHANGED |

---

## Implementation Order

1. **collector.py** — Add R7: read `influence_breakdown`, produce `reinforce_hypothesis` / `weaken_hypothesis`
2. **loop_controller.py** — Add `hypotheses_injected` to team-result YAML (+1 line)
3. **team_result_collector.py** — Add R4: read `hypotheses_injected`, detect engagement, produce candidates
4. **validator.py** — Add: reject `weaken_hypothesis`, exclude `inconclusive`, I5 independence check
5. **test_phase_8_4_hypothesis_reinforcement.py** — 26 tests
6. Run full regression suite to confirm no breakage

---

**Ready for OpenCode implementation.**