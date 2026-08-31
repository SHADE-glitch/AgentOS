```yaml
pattern_name: ai-application
scenario: AI application with retrieval/RAG or LLM capability.
task_domains: [ai, backend, database]
lead_role: system-architect
support_roles: [backend-architect, rag-engineer, llm-engineer, database-engineer, quality-evaluator]
optional_roles: [prompt-engineer, agent-engineer]
dependency_order:
  - layer: 0
    roles: [system-architect]
  - layer: 1
    roles: [backend-architect, rag-engineer, llm-engineer, database-engineer]
  - layer: 2
    roles: [quality-evaluator]
success_criteria: architecture, retrieval/LLM design, data model, and quality gate defined.
avoid_roles: [frontend-architect, frontend-performance]
effectiveness_stats:
  times_used: 0
  avg_quality_score: null
```
