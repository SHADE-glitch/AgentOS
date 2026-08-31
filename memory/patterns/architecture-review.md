```yaml
pattern_name: architecture-review
scenario: Review of an existing architecture or technical design.
task_domains: [architecture]
lead_role: technical-reviewer
support_roles: [system-architect, security-engineer]
optional_roles: [code-reviewer]
dependency_order:
  - layer: 0
    roles: [technical-reviewer]
  - layer: 1
    roles: [system-architect, security-engineer]
success_criteria: architecture risks and security posture assessed.
avoid_roles: [rag-engineer, llm-engineer, prompt-engineer, agent-engineer, frontend-performance]
effectiveness_stats:
  times_used: 0
  avg_quality_score: null
```
