```yaml
memory_id: T-001
type: task
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
tags: [ai-saas, multi-tenant, rag, isolation-strategy]
status: observed
```

# AI SaaS Multi-Tenant Platform Architecture

## Task Context

- **Task**: Design a multi-tenant AI SaaS platform with RAG capabilities
- **Difficulty**: hard
- **Single lead**: system-architect
- **Multi team**: system-architect, backend-architect, database-engineer, rag-engineer (4 roles)

## Execution Results

| mode | completeness | correctness | architecture_quality | maintainability | mean |
|------|-------------|-------------|---------------------|-----------------|------|
| single | 3 | 4 | 3 | 3 | 3.25 |
| multi | 5 | 4 | 4 | 4 | 4.25 |

- **quality_delta**: +1.00
- **cost_delta**: 2 (1 conflict + 1 extra review)
- **winner**: single (cost_delta penalty)

## Key Lessons

1. Multi-agent significantly improved completeness (3→5) and architecture quality (3→4)
2. The single-agent design missed per-tenant isolation flexibility
3. One productive conflict between system-architect and database-engineer over isolation strategy
4. The conflict was productive (led to better design) but the cost_delta rule penalized it
5. This is a borderline case: quality gain is substantial but cost_delta=2 exceeds the ≤1 threshold

## Important Decisions

- Multi-tenant isolation strategy: per-tenant schema vs shared schema debate
- The conflict resolution produced a more flexible design with per-tenant isolation_level configurability

## Observed Result

Multi-agent produces better architecture designs for complex multi-domain tasks, but coordination overhead can flip the winner rule. The cost_delta ≤ 1 rule may be too strict for tasks where conflicts are productive.