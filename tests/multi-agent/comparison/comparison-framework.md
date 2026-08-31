# Single vs Multi Comparison Framework

This framework defines how one benchmark task is run in both modes and how the winner is decided.

## Run procedure

1. Run the task in single-agent mode (router path, one expert agent). Score it. Write the result to `runtime/datasets/multi-agent/single-agent-results/<task_id>.yaml`.
2. Run the task in multi-agent mode (agent-orchestrator → collaboration-runtime). Score it. Write the result to `runtime/datasets/multi-agent/multi-agent-results/<task_id>.yaml`.
3. Score both with the fixed rubric below (two reviewers: quality-evaluator + human).
4. Write the comparison record to `runtime/datasets/multi-agent/comparison/<task_id>.yaml`.
5. Append a record to `runtime/logs/multi-agent-benchmark.md` and update `runtime/metrics/multi-agent-quality.md`.

## Scoring rubric (0-5, anchored)

- **completeness**: 5 = all `evaluation_points` covered with concrete detail; 3 = most covered, some shallow; 1 = major points missing.
- **correctness**: 5 = technically sound, no factual errors; 3 = minor errors that do not change the design; 1 = fundamental errors.
- **architecture_quality**: 5 = clear boundaries, explicit trade-offs, evolvable; 3 = workable but trade-offs unstated; 1 = tangled or unmaintainable structure.
- **maintainability**: 5 = structured, clear, reviewable; 3 = readable but inconsistent; 1 = hard to review or extend.

## Cost dimensions

- **conflicts**: number of conflicts recorded during the multi-agent run (0 for single).
- **human intervention**: `human_review_count` from the result record.

## Winner rule

- `quality_delta` = mean of the 4 quality dimensions (multi − single).
- `cost_delta` = (multi conflicts + multi human_review_count) − (single conflicts + single human_review_count).
- winner = **multi** if quality_delta > 0 AND cost_delta ≤ 1.
- winner = **single** if quality_delta ≤ 0 OR cost_delta > 1.
- otherwise **no evidence** (below the sampling rule threshold, or missing paired records).

## Comparison record schema

One per task in `runtime/datasets/multi-agent/comparison/<task_id>.yaml`:

```yaml
task_id:
winner: <single | multi | no evidence>
quality_delta: <number>
cost_delta: <number>
decision_reason: <text>
```

## Sampling rule

At least 20 paired result records (10 tasks × 2 modes) before claiming a stable conclusion. Below that, the report must state "insufficient evidence".
