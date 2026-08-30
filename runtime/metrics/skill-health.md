# Skill Health

## Objective

Track the health of each skill using operational metrics.

## Formula

```text
Health Score = usage + success rate + benchmark score - failure rate - conflict rate
```

## Example

```text
rag-engineer
- Usage: 30
- Success Rate: 93%
- Benchmark Score: 0.91
- Failure Rate: 7%
- Conflict Rate: 5%
Health: A
```

## Rule

Skills with declining health require investigation or boundary review.
