# Benchmark Runner

This directory defines the execution environment for automated benchmark runs.

## Responsibilities

- run router benchmark suite
- run skill benchmark checks
- run evolution acceptance tests
- produce benchmark-result.md for each release candidate

## Inputs

- `tests/router-benchmark.md`
- `tests/evolution-tests.md`
- `runtime/telemetry/`
- `runtime/feedback/failures/`

## Output

```text
benchmark-result.md
```
