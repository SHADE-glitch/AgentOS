```yaml
memory_id: P-001
type: pattern
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
category: cross-cutting
confidence: medium
evidence_level: runtime_validated
tags:
- cross-domain
- specialist
- team-formation
- multi-agent
- collaboration
status: observed
observation_count: 2
last_validated_at: '2026-08-30'
```

# P-001: Cross-Domain Specialist Collaboration

## Pattern Description

When a task spans 3+ technical domains, forming a multi-agent team with one specialist per domain consistently produces higher quality output than a single generalist agent.

## Observed Instances

| task | domains | team size | quality_delta | winner |
|------|---------|-----------|---------------|--------|
| arch-02 | architecture, backend, database, distributed | 4 | +1.25 | multi |
| backend-01 | backend, database, distributed | 3 | +1.00 | multi |
| ai-01 | ai, rag, database | 3 | +1.25 | multi |
| ai-02 | ai, llm, prompt, agent | 3 | +1.50 | multi |

**Average quality delta**: +1.25 (n=4)

## Pattern Mechanics

1. Each specialist contributes domain-specific patterns the generalist would miss
2. Specialist input fills gaps in the generalist's knowledge (e.g., Lua scripts, Saga patterns, vector store comparison)
3. The combination of perspectives produces concrete implementation details rather than generic designs
4. Coordination cost is manageable (cost_delta=1 in all 4 cases)

## Activation Conditions

- Task spans 3+ distinct technical domains
- Each domain requires deep specialist knowledge
- Concrete implementation patterns are expected in the deliverable
- Task difficulty is medium or hard

## Counter-Indicators

- Task is single-domain (see AP-001: Team Inflation)
- Task is easy with only 2 roles (see T-008: marginal benefit)
- Single specialist already produces quality ≥ 4.0 (see T-010: MySQL slow query)

## Evidence Level

`benchmark_evaluated` — 4 positive observations. Confidence is low due to small sample size. The pattern is consistent across observations but has not been independently validated or tested on real projects.

## Related

- S-002: Cross-Domain Architecture Collaboration (specific success cases)
- AP-001: Team Inflation (the anti-pattern of unnecessary team formation)
- T-008: SPA Performance (marginal benefit edge case)