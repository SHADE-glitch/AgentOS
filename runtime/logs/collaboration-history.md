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
