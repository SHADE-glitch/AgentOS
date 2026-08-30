```yaml
pattern_name: system-optimization
scenario: Performance, concurrency, or bottleneck optimization.
task_domains: [distributed, backend, database]
lead_role: distributed-system
support_roles: [backend-architect, database-engineer]
optional_roles: [code-reviewer, system-architect]
dependency_order:
  - layer: 0
    roles: [distributed-system]
  - layer: 1
    roles: [backend-architect, database-engineer]
success_criteria: bottleneck identified and optimization plan validated.
avoid_roles: [rag-engineer, llm-engineer, prompt-engineer, agent-engineer, frontend-architect]
effectiveness_stats:
  times_used: 0
  avg_quality_score: null
```
