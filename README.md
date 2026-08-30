# Agent OS

This repository is the operating system layer for the Agent OS runtime, skills, knowledge, and learning loop.

## Core runtime control loop

The system is organized around an evidence-based quality loop:

```text
Task execution
  -> telemetry capture
  -> quality evaluation
  -> regression detection
  -> benchmark execution
  -> dashboard and reporting
  -> release recommendation or follow-up work
```

## Included capability areas

- Telemetry: `runtime/telemetry/`
- Quality evaluation: `skills/meta/quality-evaluator/`
- Regression detection: `tests/regression/`
- Benchmark execution: `tests/benchmark-runner/`
- Dashboard and reporting: `runtime/dashboard.md`, `runtime/metrics/`, `runtime/versioning/`
- Feedback and improvement intake: `runtime/feedback/`

## Phase 4 follow-up readiness

The implementation is intentionally structured to support the next phase of operational hardening:

- capture runtime evidence from major tasks
- compare before/after quality signals
- flag regressions against benchmark baselines
- run release-oriented validation benchmarks
- surface decisions through the runtime dashboard and release status summary

This repository is ready for a Phase 4 follow-up that focuses on execution validation, quality gates, and continuous improvement automation.
