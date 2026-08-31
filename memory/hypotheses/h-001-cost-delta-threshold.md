```yaml
memory_id: H-001
type: hypothesis
created_at: 2026-08-30
source:
  type: benchmark
  sources:
    - task_id: arch-01
      run_id: round0
      mode: multi
    - task_id: backend-02
      run_id: round0
      mode: multi
category: cross-cutting
confidence: low
evidence_level: benchmark_evaluated
tags: [winner-rule, cost-delta, threshold, calibration, quality-assessment]
status: observed
```

# H-001: Cost Delta Threshold Calibration

## Hypothesis

The winner rule's cost_delta threshold should be adjusted from ≤1 to ≤2.

## Current Rule

```yaml
winner: multi if quality_delta > 0 AND cost_delta ≤ 1
winner: single if quality_delta ≤ 0 OR cost_delta > 1
```

## Evidence

### Borderline Cases (quality_delta > 0, cost_delta = 2)

| task | quality_delta | cost_delta | current_winner | proposed_winner |
|------|---------------|------------|----------------|-----------------|
| arch-01 | +1.00 | 2 | single | **multi** |
| backend-02 | +1.50 | 2 | single | **multi** |

### Analysis
- arch-01: +1.00 quality gain, conflict was productive (better isolation strategy)
- backend-02: +1.50 quality gain (largest in Round 0), conflict was productive (PCI-DSS compliance)
- Both conflicts were productive, not wasteful
- The current ≤1 threshold penalizes tasks where specialists disagree productively
- A ≤2 threshold would correctly classify both as multi wins

### Impact of Change
- Total multi wins: 7 → 9
- Total single wins: 3 → 1 (only opt-02 remains)
- This aligns with the qualitative assessment that both arch-01 and backend-02 benefited from multi-agent

## Counter-Arguments

- Only 2 borderline cases observed (n=10)
- Sample size is too small to justify a rule change
- The current threshold is conservative and safe
- Relaxing the threshold may encourage unnecessary team formation

## Test Plan

- Round 1 benchmark should preserve the original threshold (≤1) for comparison
- After Round 1 (n=20), re-evaluate the cost_delta distribution
- If the pattern persists, consider a weighted threshold that accounts for conflict productivity

## Status

**Hypothesis** — not yet tested. This is a proposed rule change based on Round 0 evidence. No change has been applied to the winner rule. The original ≤1 threshold is preserved for Round 1.

## Related

- T-001: AI SaaS Platform (arch-01 borderline)
- T-004: Payment System (backend-02 borderline)
- F-001: Isolation Strategy Conflict (productive conflict)
- F-002: Card Data Storage Conflict (productive conflict)