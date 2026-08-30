# Evolution Safety

## Objective

Prevent system degradation after skill or router updates.

## Template

```text
Before:
- Router accuracy: 85%
- Failure rate: 12%

Change:
- Added or modified skill or router rule

After:
- Router accuracy: 90%
- Failure rate: 10%

Result:
- Improvement: +5%
- Regression: none
```

## Rule

Any change must be judged on before/after evidence. A change is only safe if it improves or maintains quality without creating unresolved regressions.
