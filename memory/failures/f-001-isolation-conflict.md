```yaml
memory_id: F-001
type: failure
created_at: 2026-08-30
source:
  type: benchmark
  task_id: arch-01
  run_id: round0
  mode: multi
  file: runtime/datasets/multi-agent/comparison/arch-01.yaml
category: architecture
confidence: low
evidence_level: benchmark_evaluated
tags: [collaboration, isolation-strategy, conflict, productive-conflict]
status: observed
```

# F-001: Isolation Strategy Conflict

## Symptom

During the multi-tenant AI SaaS platform design, a conflict arose between the system-architect and database-engineer over the multi-tenant isolation strategy.

## Root Cause

The system-architect proposed a shared-schema approach for operational simplicity, while the database-engineer advocated for per-tenant schema isolation for stronger data boundaries. The conflict stemmed from different architectural priorities: simplicity vs isolation guarantees.

## Impact

- 1 additional human review cycle required
- cost_delta increased to 2, causing the winner rule to flip from multi to single
- The conflict was **productive** — it led to a better design

## Correction

The resolution produced a flexible design with per-tenant isolation_level configurability, allowing the system to support both shared-schema (for small tenants) and per-tenant schema (for enterprise tenants).

## Prevention

Consider including the database-engineer in the initial architecture phase rather than in a subsequent review cycle. Earlier integration of specialist concerns may reduce late-stage conflicts.

## Evidence Level

`benchmark_evaluated` — single observation in Round 0. Not yet validated across multiple tasks.

## Note

This is classified as a "failure" because it increased coordination cost, but the conflict itself was productive. The lesson is about **sequencing** (when specialists join), not about the conflict being harmful.