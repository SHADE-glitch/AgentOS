# Routing History

This file keeps the decision trail for agent routing.

## Record format

```text
Date:
Task:
User Intent:
Lead Skill:
Supporting Skills:
Route Quality: Correct / Needs Review / Wrong
Reason:
Observed Issue:
Follow-up:
```

## Example records

```text
Date: 2026-08-30
Task: 设计订单系统
User Intent: Architecture
Lead Skill: system-architect
Supporting Skills: backend-architect, database-engineer
Route Quality: Correct
Reason: Requires end-to-end design plus storage concerns.
Observed Issue: Inventory consistency analysis was missing.
Follow-up: Add distributed-system support when consistency or stock reservation is involved.
```

```text
Date: 2026-08-30
Task: Redis 缓存击穿排查
User Intent: Debug
Lead Skill: database-engineer
Supporting Skills: backend-architect
Route Quality: Correct
Reason: This is primarily a storage/cache issue with service impact.
Observed Issue: None.
Follow-up: Continue to document cache avalanche and cache breakdown patterns.
```

## Review rule

After every significant route decision, ask:

- Was the lead skill correct?
- Were supporting skills missing?
- Did the user need a more specific skill?
- Was a broader skill used without justification?

## Use in optimization

These records should be used by:

- `agent-router` to refine priority rules
- `agent-evolution-engineer` to detect route drift
- `runtime/dashboard.md` to track route quality over time
