```yaml
memory_id: P-002
type: pattern
created_at: 2026-08-30
source:
  type: benchmark
  sources:
    - task_id: backend-02
      run_id: round0
      mode: multi
    - task_id: fe-01
      run_id: round0
      mode: multi
category: cross-cutting
confidence: low
evidence_level: benchmark_evaluated
tags: [security, team-formation, role-ordering, pci-dss, rbac]
status: observed
```

# P-002: Security-First Team Formation

## Pattern Description

For tasks with security or compliance requirements, the security specialist should be included in the initial architecture phase (layer 0), not introduced as a reviewer (layer 1). Late security integration causes productive but costly conflicts.

## Observed Instances

### Positive: fe-01 (security integrated early)
- **Task**: Admin platform with RBAC
- **Team**: frontend-architect, backend-architect, code-reviewer (3 roles)
- **Result**: RBAC model was co-designed from the start, no late conflicts
- **quality_delta**: +1.00, cost_delta=1, **multi win**

### Negative: backend-02 (security integrated late)
- **Task**: Payment system with PCI-DSS
- **Team**: backend-architect, database-engineer, distributed-system, security-engineer (4 roles)
- **Result**: Security-engineer entered after data model was designed, causing conflict and redesign
- **quality_delta**: +1.50, cost_delta=2, **single win** (penalty)

## Pattern Mechanics

1. Security requirements touch the data model, API design, and deployment architecture
2. Introducing security after these are designed forces costly redesign
3. When security is in layer 0, the design is built secure from the start
4. The quality gain from security integration is large (+1.50), but the cost penalty from late integration can flip the winner

## Activation Conditions

- Task involves sensitive data (PII, payment, credentials)
- Compliance requirements (PCI-DSS, GDPR, HIPAA)
- Authentication/authorization is a core requirement

## Team Formation Rule

For security-sensitive tasks, the security-engineer should be in the **first team formation wave** alongside the primary architect, not in a subsequent review wave.

## Evidence Level

`benchmark_evaluated` — 2 observations (1 positive, 1 negative). Confidence is low. The pattern is derived from contrasting two cases; more data is needed for validation.

## Related

- F-002: Card Data Storage Conflict (the negative case)
- T-007: Admin Platform (the positive case)
- T-004: Payment System (the task with security penalty)