```yaml
memory_id: H-002
type: hypothesis
created_at: 2026-08-30
source:
  type: benchmark
  sources:
    - task_id: arch-02
      run_id: round0
      mode: multi
    - task_id: backend-01
      run_id: round0
      mode: multi
    - task_id: ai-01
      run_id: round0
      mode: multi
    - task_id: ai-02
      run_id: round0
      mode: multi
    - task_id: fe-01
      run_id: round0
      mode: multi
    - task_id: opt-01
      run_id: round0
      mode: multi
category: cross-cutting
confidence: low
evidence_level: benchmark_evaluated
tags: [multi-agent, complexity, routing, team-formation, task-classification]
status: observed
```

# H-002: Multi-Agent Preference for Complex Cross-Domain Tasks

## Hypothesis

Multi-agent collaboration is preferred (quality delta > 0, cost_delta manageable) for tasks that are:
1. Hard or medium difficulty, AND
2. Span 3+ technical domains

## Evidence

### Multi Wins (7/10 tasks)

| task | difficulty | domains | team_size | delta |
|------|------------|---------|-----------|-------|
| arch-02 | hard | 4 | 4 | +1.25 |
| backend-01 | medium | 3 | 3 | +1.00 |
| ai-01 | medium | 3 | 3 | +1.25 |
| ai-02 | medium | 3 | 3 | +1.50 |
| fe-01 | medium | 3 | 3 | +1.00 |
| opt-01 | hard | 3 | 3 | +1.00 |
| fe-02 | easy | 2 | 2 | +0.75 |

### Single Wins (3/10 tasks)

| task | difficulty | domains | team_size | delta | reason |
|------|------------|---------|-----------|-------|--------|
| opt-02 | easy | 1 | 1 | 0.00 | single-domain, correct |
| arch-01 | hard | 4 | 4 | +1.00 | cost_delta penalty |
| backend-02 | medium | 4 | 4 | +1.50 | cost_delta penalty |

### Analysis

- Every multi win task has 3+ domains and medium+ difficulty
- The 2 single wins (arch-01, backend-02) have quality delta > 0 but were penalized by cost_delta
- If cost_delta threshold were ≤2, all 3+ domain tasks would be multi wins
- The only true single-only task is opt-02 (1 domain, easy)

## Hypothesis Statement

```yaml
routing_rule: >
  IF task_domains ≥ 3 AND difficulty ∈ {medium, hard}
  THEN multi-agent is preferred
  ELSE single-agent is sufficient
```

## Test Plan

- Round 1 should include tasks with 2 domains to test the boundary
- Include a hard task with 1 domain to test the interaction of difficulty and domain count
- Include an easy task with 3 domains to test the lower bound

## Status

**Hypothesis** — based on Round 0 evidence (7/7 multi wins for 3+ domain tasks, excluding cost_delta penalties). Not yet validated with independent data.

## Related

- P-001: Cross-Domain Specialist Collaboration (the pattern)
- T-010: MySQL Slow Query (the counter-example: 1 domain, single is sufficient)
- H-001: Cost Delta Threshold (interaction with this hypothesis)