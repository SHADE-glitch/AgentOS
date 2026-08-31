# comparison/

One comparison record per task, named `<task_id>.yaml`, using the comparison record schema defined in `tests/multi-agent/comparison/comparison-framework.md`.

Each record computes the winner from the paired single/multi result files.

## Worked example

```yaml
task_id: arch-01
winner: multi
quality_delta: 1.0
cost_delta: 1
decision_reason: multi covered all evaluation points and added retrieval strategy; one conflict was resolved by the lead without human escalation.
```
