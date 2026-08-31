# Multi-Agent Quality Metrics

This file tracks the single vs multi benchmark metrics. It is the evidence source for the Phase 4.4 conclusion: does multi-agent collaboration produce real quality gains?

## Metrics

```yaml
task_success_rate: completed tasks / total tasks
coverage: tasks with BOTH single and multi result records / total tasks
quality_score: mean of the 4 quality dimensions per mode (single mean, multi mean, delta)
conflict_rate: total conflicts / multi-agent tasks
avg_agents: mean team size across multi runs
human_review_count: mean interventions per task
token_efficiency: quality_score / max(1, avg_agents)   # v1 proxy
```

## Round 0 Values

```yaml
task_success_rate: 1.00
coverage: 1.00
single_quality_score_mean: 3.025
multi_quality_score_mean: 4.125
quality_delta: +1.10
conflict_rate: 0.20
avg_agents: 2.9
human_review_count: 1.9
token_efficiency: 1.42
records: 20
```

## Per-Task Summary

| task_id | category | difficulty | single_mean | multi_mean | delta | winner |
|---------|----------|------------|-------------|------------|-------|--------|
| arch-01 | architecture | hard | 3.25 | 4.25 | +1.00 | single |
| arch-02 | architecture | hard | 3.00 | 4.25 | +1.25 | multi |
| backend-01 | backend | medium | 3.00 | 4.00 | +1.00 | multi |
| backend-02 | backend | medium | 2.75 | 4.25 | +1.50 | single |
| ai-01 | ai | medium | 3.00 | 4.25 | +1.25 | multi |
| ai-02 | ai | medium | 2.75 | 4.25 | +1.50 | multi |
| fe-01 | frontend | medium | 3.00 | 4.00 | +1.00 | multi |
| fe-02 | frontend | easy | 3.00 | 3.75 | +0.75 | multi |
| opt-01 | optimization | hard | 3.00 | 4.00 | +1.00 | multi |
| opt-02 | optimization | easy | 4.00 | 4.00 | 0.00 | single |

## Winner Summary

- multi wins: 7 (arch-02, backend-01, ai-01, ai-02, fe-01, fe-02, opt-01)
- single wins: 3 (arch-01, backend-02, opt-02)
- cost_delta penalty: 2 of 3 single wins are due to cost_delta > 1 despite positive quality_delta

## Sampling Rule

20 paired result records (10 tasks × 2 modes) collected. Sampling rule satisfied. Evidence status: sufficient.