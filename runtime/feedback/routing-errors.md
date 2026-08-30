# Routing Errors

This file records mistaken route assignments.

## Record format

```text
Date:
User Task:
Expected Lead Skill:
Selected Lead Skill:
Issue Type: wrong-route / missing-support / over-broad / under-specific
Why It Was Wrong:
Remediation:
```

## Example

```text
Date: 2026-08-30
User Task: Redis 缓存击穿排查
Expected Lead Skill: database-engineer
Selected Lead Skill: backend-architect
Issue Type: wrong-route
Why It Was Wrong: route was too broad and did not prioritize storage-specific expertise
Remediation: tighten database-engineer priority for cache and SQL optimization tasks
```

## Use in router tuning

This file should feed directly into:

- `agent-router` priority adjustments
- `skill-routing-matrix.md`
- `agent-evolution-engineer` review findings
