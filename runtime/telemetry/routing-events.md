# Routing Events

## Event format

```yaml
event_id: R-000
timestamp: 2026-08-30T15:00:00Z
task_type: "Architecture"
route_input: "高并发订单系统设计"
selected_skill: "distributed-system"
support_skills:
  - "system-architect"
  - "database-engineer"
expected_skill: "distributed-system"
route_confidence: 0.91
incorrect_route: false
fallback_used: false
```

## Purpose

This record tracks whether the router made the correct call and whether the supporting skill set was complete.
