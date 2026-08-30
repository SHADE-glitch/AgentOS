```yaml
pattern_name: full-stack-product
scenario: Full product with UI, backend, and optional AI features.
task_domains: [frontend, backend, database]
lead_role: system-architect
support_roles: [backend-architect, database-engineer, frontend-architect, code-reviewer]
optional_roles: [llm-engineer, rag-engineer, distributed-system, testing-engineer, devops-engineer]
dependency_order:
  - layer: 0
    roles: [system-architect]
  - layer: 1
    roles: [backend-architect, database-engineer, frontend-architect]
  - layer: 2
    roles: [code-reviewer]
success_criteria: end-to-end architecture across UI, backend, and data.
avoid_roles: []
effectiveness_stats:
  times_used: 0
  avg_quality_score: null
```
