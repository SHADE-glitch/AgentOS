# Router Metrics

This file tracks how accurately the router selects specialist roles.

## Metrics

- route accuracy
- wrong route count
- missing support role count
- ambiguous task count
- fallback rate
- multi-turn continuity rate

## Template

```text
Period:
Total Routes:
Correct Routes:
Wrong Routes:
Ambiguous Routes:
Fallback Used:
Missing Support Role Count:
Observations:
```

## Example

```text
Period: 2026-08-30
Total Routes: 32
Correct Routes: 27
Wrong Routes: 3
Ambiguous Routes: 2
Fallback Used: 1
Missing Support Role Count: 4
Observations: SQL issues are slightly over-routed to backend-architect instead of database-engineer.
```

## Improvement rule

When route quality falls below expectation, update:

- priority rules
- domain-to-skill mapping
- fallback behavior
- supporting-agent selection logic
