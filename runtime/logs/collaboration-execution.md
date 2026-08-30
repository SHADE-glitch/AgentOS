# Collaboration Execution Log

This file records each multi-agent team execution managed by `skills/meta/collaboration-runtime/`.

## Record format

```yaml
team_id:
task:
agents:
execution_order:
handoffs:
conflicts:
final_quality:
```

## Field meanings

- team_id: the team plan id from the orchestrator
- task: task id and short description
- agents: roles that participated (lead first)
- execution_order: the actual layer-by-layer execution sequence
- handoffs: handoff ids and their validation results
- conflicts: conflicts found, their types, and resolutions
- final_quality: quality signal from quality-evaluator

## Example

```yaml
team_id: T-001
task: AI电商推荐系统设计
agents: [system-architect, backend-architect, rag-engineer, database-engineer, quality-evaluator]
execution_order:
  - layer 0: [system-architect]
  - layer 1: [backend-architect, rag-engineer, database-engineer]
  - layer 2: [quality-evaluator]
handoffs:
  - H-001: system-architect -> backend-architect (valid)
  - H-002: system-architect -> rag-engineer (valid)
  - H-003: system-architect -> database-engineer (valid)
conflicts: []
final_quality: pending
```

## Relation chain

- `runtime/logs/team-formation-history.md` — the formation decision that precedes execution
- This file — the execution records (realizing the Phase 4.1 future fields)
- `runtime/logs/collaboration-history.md` — retrospective observation and quality review
