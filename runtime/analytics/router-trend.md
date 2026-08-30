# Router Trend Analysis

## Goal

Detect if router quality is improving, flat, or regressing over time.

## Example

```text
Week 1: 82%
Week 2: 86%
Week 3: 89%
Trend: improving
```

## Decision rule

A router trend is considered stable only when it remains above the target threshold and does not show repeated regression after changes.
