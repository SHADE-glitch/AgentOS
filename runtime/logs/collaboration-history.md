# Collaboration History

This file records how multi-agent collaboration actually behaves in practice.

## Record format

```text
Date:
Lead Agent:
Supporting Agents:
Task:
Handoff Quality: Clear / Mildly Clear / Weak
Outcome:
Issue:
Next Action:
```

## Example

```text
Date: 2026-08-30
Lead Agent: system-architect
Supporting Agents: backend-architect, database-engineer, distributed-system
Task: 设计秒杀系统
Handoff Quality: Clear
Outcome: Good
Issue: Consistency and inventory reservation needed stronger emphasis.
Next Action: Add a distributed consistency decision section in the system-architect workflow.
```

## Collaboration rule

Multi-agent work should be efficient and explicit.
If collaboration quality degrades, review:

- unclear task boundaries
- missing supporting agents
- weak handoff format
- unbalanced lead responsibility

## Phase 4.1 future record fields

Once multi-agent team execution starts (Phase 4.2+), each collaboration record will use these fields:

```yaml
task:
team:
agents:
execution_order:
conflicts:
quality_score:
```

Field meanings:

- task: task id and short description
- team: the team plan / pattern used
- agents: roles that participated
- execution_order: actual dependency-ordered execution sequence
- conflicts: conflicts found and how they were resolved
- quality_score: final quality signal from the evaluation layer
