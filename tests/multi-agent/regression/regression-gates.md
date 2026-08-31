# Regression Gates

Three gates protect the multi-agent layer from silent regressions. Any gate failure blocks the release and creates an evolution-engine improvement proposal.

## G1 — Team formation

- Measure: `../team-formation/team-formation-benchmark.md` pass rate.
- Threshold: must stay 3/3.

## G2 — Collaboration failure

- Measure: Type E (Coordination Failure) records in `runtime/feedback/failures/pending/` and `analyzed/` per benchmark round.
- Threshold: must not increase vs the previous round baseline.

## G3 — Quality

- Measure: multi-agent mean quality_score and the single-vs-multi delta in `runtime/metrics/multi-agent-quality.md`.
- Threshold: must not drop below the previous comparison report values.

## Round 0 Baseline

```yaml
round: 0
g1_formation_pass_rate: 3/3
g2_type_e_count: 0
g3_multi_quality_mean: 4.125
g3_quality_delta: +1.10
```

## Round 0 Gate Check

- G1: Team formation 3/3 benchmark PASS (Team Inflation Guard correctly blocked opt-02)
- G2: Type E count = 0, PASS
- G3: multi_quality_mean = 4.125, quality_delta = +1.10, PASS

## Rule

If any gate fails: block the release, record the failure with evidence, and create an improvement proposal via the evolution-engine pipeline.