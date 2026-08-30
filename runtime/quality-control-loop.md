# Phase 3.4 Runtime Intelligence and Evaluation

## Objective

Provide a measurable quality-control loop for the Agent OS so routing, skill execution, and evolution changes are evaluated with runtime evidence instead of assumptions.

## Runtime control loop

```text
Task execution
  -> record telemetry event
  -> summarize task outcome and quality score
  -> evaluate benchmark and failure evidence
  -> detect regressions against the prior baseline
  -> run release benchmark validation
  -> update dashboard and release recommendation
```

## Required artifacts

- Telemetry: `runtime/telemetry/`
- Quality evaluator: `skills/meta/quality-evaluator/`
- Regression detection: `tests/regression/`
- Benchmark runner: `tests/benchmark-runner/`
- Dashboard artifacts: `runtime/dashboard.md`, `runtime/metrics/`, `runtime/versioning/`

## Quality gate

The quality gate is active when:

- every major task emits telemetry
- the evaluator compares before/after quality states
- regression checks are recorded under `tests/regression/`
- benchmark output is recorded as a pass/fail/hold result
- the dashboard shows router accuracy, failure counts, regressions, and recent improvements
- release approval requires benchmark evidence and human review

## Release recommendation rules

- PASS: benchmark evidence supports improvement, no unresolved regression
- FAIL: benchmark evidence shows reduced quality or unresolved regressions
- HOLD: evidence is incomplete, risky, or not yet validated

This is the runtime intelligence and evaluation system for Phase 3.4.
