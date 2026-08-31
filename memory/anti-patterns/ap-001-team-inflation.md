```yaml
memory_id: AP-001
type: anti-pattern
created_at: 2026-08-30
source:
  type: benchmark
  sources:
    - task_id: opt-02
      run_id: round0
      mode: single
    - task_id: fe-02
      run_id: round0
      mode: multi
category: optimization
confidence: low
evidence_level: benchmark_evaluated
tags: [team-inflation, single-domain, unnecessary-team, orchestrator, guard]
status: observed
```

# AP-001: Team Inflation

## Anti-Pattern Description

Forming a multi-agent team for a single-domain task that a single specialist can handle well. This adds coordination cost without quality improvement.

## Observed Instances

### Prevention Proof: opt-02 (MySQL slow query)
- **Task**: MySQL slow query optimization (single-domain, easy)
- **Orchestrator**: Correctly refused to form a team (Team Inflation Guard: PASSED)
- **Single quality**: 4.00 (already excellent)
- **Multi quality**: N/A (correctly blocked)
- **Evidence**: The orchestrator's activation condition logic works correctly

### Borderline: fe-02 (SPA performance)
- **Task**: SPA performance optimization (single-domain, easy)
- **Team**: 2 roles (below the ≥3 threshold)
- **quality_delta**: +0.75 (marginal)
- **Verdict**: Multi wins by rule, but +0.75 is not worth the +1 coordination cost
- **Lesson**: This task should have been blocked by the Team Inflation Guard

## Anti-Pattern Mechanics

1. A single-domain task is routed to the orchestrator
2. The orchestrator forms a team because the routing logic allows it
3. The additional specialists add marginal value at best
4. Coordination cost is incurred for negligible benefit
5. Net result: wasted resources

## Prevention

- **Orchestrator must enforce the ≥3 role activation threshold**
- **Single-domain tasks should bypass the orchestrator entirely**
- **Single-agent quality ≥ 4.0 should trigger automatic single-agent routing**

## Related

- T-010: MySQL Slow Query (the prevention proof)
- T-008: SPA Performance (the borderline case)
- P-001: Cross-Domain Collaboration (the pattern this anti-pattern contrasts with)