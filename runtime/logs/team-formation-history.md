# Team Formation History

This file records every team formation decision made by `agent-orchestrator`.

## Record format

```yaml
task:
matched_pattern:
selected_agents:
rejected_agents:
reason:
quality_result:
```

## Field meanings

- task: task id and short description
- matched_pattern: the pattern from `memory/patterns/` that matched
- selected_agents: final team (lead first)
- rejected_agents: roles pruned or avoided, with the rule that rejected them
- reason: why this pattern matched and why roles were selected or rejected
- quality_result: benchmark or quality signal, filled after review

## Example

```yaml
task: AI电商推荐系统设计
matched_pattern: ai-application
selected_agents: [system-architect, backend-architect, rag-engineer, database-engineer, quality-evaluator]
rejected_agents:
  - llm-engineer: no LLM application/model design signal (R5)
  - prompt-engineer: optional, not required
  - agent-engineer: optional, not required
reason: domains ai + backend + database matched ai-application; retrieval signal kept rag-engineer
quality_result: pending
```

## Relation to collaboration-history

`collaboration-history.md` records execution-level collaboration (Phase 4.3+). This file records the formation decision that precedes execution. Every team formation should leave exactly one record here.
