```yaml
pattern_name: backend-project
scenario: Standard backend service or CRUD admin system (Spring Boot, APIs, forms).
task_domains: [backend, database]
lead_role: backend-architect
support_roles: [database-engineer, testing-engineer]
optional_roles: [code-reviewer, devops-engineer, system-architect]
dependency_order:
  - layer: 0
    roles: [backend-architect]
  - layer: 1
    roles: [database-engineer]
  - layer: 2
    roles: [testing-engineer]
success_criteria: service boundaries, data model, and test strategy defined.
avoid_roles: [rag-engineer, llm-engineer, prompt-engineer, agent-engineer, frontend-architect, quality-evaluator]
effectiveness_stats:
  times_used: 0
  avg_quality_score: null
```
