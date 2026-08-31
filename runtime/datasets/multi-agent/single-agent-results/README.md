# single-agent-results/

One result file per task, named `<task_id>.yaml`, using the result record schema in `../README.md`.

Records here are the single-agent baseline. Each must be produced by a single expert agent (no team) before the multi-agent run of the same task.

## Worked example

```yaml
task_id: arch-01
mode: single
executed_roles: [system-architect]
quality_scores:
  completeness: 3
  correctness: 4
  architecture_quality: 3
  maintainability: 3
conflicts: 0
human_review_count: 1
notes: solid overall architecture but missed retrieval evaluation strategy.
```
