# multi-agent-results/

One result file per task, named `<task_id>.yaml`, using the result record schema in `../README.md`.

Records here are the multi-agent team runs: the task went through agent-orchestrator (team formation) and collaboration-runtime (execution), and the final integration report was scored.

## Worked example

```yaml
task_id: arch-01
mode: multi
executed_roles: [system-architect, backend-architect, database-engineer, rag-engineer]
quality_scores:
  completeness: 5
  correctness: 4
  architecture_quality: 4
  maintainability: 4
conflicts: 1
human_review_count: 2
notes: one architecture conflict resolved by the lead; retrieval evaluation covered.
```
