# Task Events

## Event examples

```yaml
event_id: T-001
timestamp: 2026-08-30T15:00:00Z
task_type: "Architecture"
selected_skill: "rag-engineer"
support_skills:
  - "llm-engineer"
  - "database-engineer"
execution_result: "Good"
success: true
failure_id: null
latency_ms: 2900
quality_score: 0.91

---

event_id: T-002
timestamp: 2026-08-30T15:12:00Z
task_type: "Debug"
selected_skill: "database-engineer"
support_skills:
  - "backend-architect"
execution_result: "Good"
success: true
failure_id: "F-003"
latency_ms: 3400
quality_score: 0.94

---

event_id: T-003
timestamp: 2026-08-30T15:24:00Z
task_type: "Architecture"
selected_skill: "distributed-system"
support_skills:
  - "system-architect"
  - "database-engineer"
execution_result: "Good"
success: true
failure_id: "F-002"
latency_ms: 4100
quality_score: 0.90
```

## Purpose

This record captures the outcome of a task execution, including the lead skill, supporting skills, latency, and a quality score. These records are evidence for the production validation layer.
