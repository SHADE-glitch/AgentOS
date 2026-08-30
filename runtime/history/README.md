# Runtime History

This directory stores historical operational records to support long-term trend analysis.

## Period buckets

- `daily/`
- `weekly/`
- `monthly/`
- `snapshots/`

## Record format

```yaml
period: "2026-W35"
tasks_processed: 28
router_accuracy: 0.89
skill_success_rate: 0.9
failure_count: 3
evolution_changes: 2
regression_count: 0
quality_score: 0.88
```

## Principle

Data must accumulate over time so the system can detect stability, drift, and regression rather than reacting to a single moment in time.
