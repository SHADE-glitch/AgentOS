# Routing Events

## Event examples

```yaml
event_id: R-001
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

---

event_id: R-002
timestamp: 2026-08-30T15:04:00Z
task_type: "AI"
route_input: "RAG 推荐系统设计"
selected_skill: "rag-engineer"
support_skills:
  - "llm-engineer"
  - "database-engineer"
expected_skill: "rag-engineer"
route_confidence: 0.90
incorrect_route: false
fallback_used: false

---

event_id: R-003
timestamp: 2026-08-30T15:08:00Z
task_type: "Debug"
route_input: "MySQL SQL 慢查询分析"
selected_skill: "database-engineer"
support_skills:
  - "backend-architect"
expected_skill: "database-engineer"
route_confidence: 0.93
incorrect_route: false
fallback_used: false
```

## Purpose

This record tracks whether the router made the correct call and whether the supporting skill set was complete. These events form the live telemetry evidence for the readiness gate.
