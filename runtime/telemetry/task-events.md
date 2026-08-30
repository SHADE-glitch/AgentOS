# Task Events

## Event format

```yaml
event_id: T-000
timestamp: 2026-08-30T15:00:00Z
task_type: "Architecture / Coding / Debug / Review / Optimization / Learning / Research"
selected_skill: "backend-architect"
support_skills:
  - "system-architect"
  - "database-engineer"
execution_result: "Good"
success: true
failure_id: "F-001"
latency_ms: 3200
quality_score: 0.88
```

## Purpose

This record captures the outcome of a task execution, including the lead skill, supporting skills, latency, and a quality score.
