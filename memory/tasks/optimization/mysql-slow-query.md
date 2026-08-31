```yaml
memory_id: T-010
type: task
created_at: 2026-08-30
source:
  type: benchmark
  task_id: opt-02
  run_id: round0
  mode: single
  file: runtime/datasets/multi-agent/comparison/opt-02.yaml
category: optimization
confidence: low
evidence_level: benchmark_evaluated
tags: [mysql, slow-query, single-domain, team-inflation-guard]
status: observed
```

# MySQL Slow Query Optimization

## Task Context

- **Task**: Optimize MySQL slow queries
- **Difficulty**: easy
- **Single lead**: database-engineer
- **Multi team**: N/A (Team Inflation Guard blocked formation)

## Execution Results

| mode | completeness | correctness | architecture_quality | maintainability | mean |
|------|-------------|-------------|---------------------|-----------------|------|
| single | 4 | 4 | 4 | 4 | 4.00 |
| multi | N/A | N/A | N/A | N/A | N/A |

- **quality_delta**: 0.00 (multi-agent not executed)
- **cost_delta**: 0
- **winner**: single

## Key Lessons

1. **Team Inflation Guard: PASSED** — the orchestrator correctly refused to form a team
2. This is a single-domain, single-role task (database-engineer only)
3. The single-agent already produced high-quality output (4.00)
4. Multi-agent would have added zero value and unnecessary coordination cost
5. This validates the orchestrator's activation condition logic

## Important Decisions

- Index optimization strategy
- Query plan analysis and rewriting
- Database configuration tuning

## Observed Result

Single-domain, single-role tasks should remain single-agent. The orchestrator's Team Inflation Guard correctly prevented unnecessary team formation. This is the canonical example of when NOT to use multi-agent: the task is well-defined, single-domain, and the single specialist already produces excellent output.

**This task is the primary evidence for the Team Inflation Guard anti-pattern prevention.**