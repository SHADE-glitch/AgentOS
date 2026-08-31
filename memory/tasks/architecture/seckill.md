```yaml
memory_id: T-002
type: task
created_at: 2026-08-30
source:
  type: benchmark
  task_id: arch-02
  run_id: round0
  mode: multi
  file: runtime/datasets/multi-agent/comparison/arch-02.yaml
category: architecture
confidence: low
evidence_level: benchmark_evaluated
tags: [seckill, high-concurrency, lua, idempotency, distributed]
status: observed
```

# Seckill System Architecture

## Task Context

- **Task**: Design a high-concurrency seckill (flash sale) system
- **Difficulty**: hard
- **Single lead**: system-architect
- **Multi team**: system-architect, backend-architect, database-engineer, distributed-system (4 roles)

## Execution Results

| mode | completeness | correctness | architecture_quality | maintainability | mean |
|------|-------------|-------------|---------------------|-----------------|------|
| single | 3 | 3 | 3 | 3 | 3.00 |
| multi | 4 | 4 | 5 | 4 | 4.25 |

- **quality_delta**: +1.25
- **cost_delta**: 1 (1 extra human review)
- **winner**: multi

## Key Lessons

1. Multi-agent added concrete implementation details: Lua atomic inventory script, idempotency key, Kafka-based async order flow
2. The seckill-specific table schema was a key improvement over the generic single-agent design
3. Distributed-system specialist contributed critical concurrency patterns
4. Clear multi win for a hard cross-domain task

## Important Decisions

- Lua script for atomic inventory deduction in Redis
- Idempotency key design for exactly-once ordering
- Kafka async order flow to decouple seckill from order processing

## Observed Result

Hard cross-domain tasks (seckill spans architecture, database, distributed systems) benefit significantly from specialist collaboration. The quality gain is substantial and coordination cost is acceptable.