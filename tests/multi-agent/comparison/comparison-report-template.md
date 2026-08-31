# Comparison Report

## Dataset Summary
- tasks: <count>
- categories: <count>
- paired records (single + multi): <count of 20 required>
- evidence status: <sufficient / insufficient evidence>

## Per-Task Comparison Table

| task_id | category | single mean | multi mean | quality_delta | cost_delta | winner |
|---|---|---|---|---|---|---|
| <id> | <cat> | <x.x> | <x.x> | <+x.x> | <x> | <single / multi / no evidence> |

## Aggregate Metrics

- task_success_rate:
- coverage:
- single quality_score mean:
- multi quality_score mean:
- quality delta (overall):
- conflict_rate:
- avg_agents:
- human_review_count:
- token_efficiency:

## Winner Analysis

- multi wins: <count>
- single wins: <count>
- no evidence: <count>
- interpretation: <what the pattern means — e.g. multi wins on hard cross-domain tasks, single wins on easy tasks>

## Regression Check

- G1 team formation 3/3: <pass / fail>
- G2 Type E failures vs previous round: <pass / fail>
- G3 quality vs previous report: <pass / fail>

## Improvement Decision

- <continue multi-agent / fix team formation / revert to single-agent>
- rationale: <evidence-based, citing the comparison records>

## Evidence Requirements

- [ ] every task has both single and multi result records
- [ ] every comparison record cites paired result files
- [ ] every winner follows the winner rule in `comparison-framework.md`
- [ ] sampling rule satisfied before any trend claim
