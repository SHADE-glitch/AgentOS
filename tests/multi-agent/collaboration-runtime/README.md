# Collaboration Runtime Benchmark

Validates Phase 4.3 collaboration runtime: dependency scheduling, handoff enforcement, conflict routing, and result aggregation.

## How to run

1. Feed the case `## Input` to the system.
2. Compare the runtime behavior against `## Expected`.
3. Record pass / fail with reason.

## Pass criteria

- exact behavior match for scheduling, handoff, conflict, and aggregation
- every action leaves a trace in `runtime/logs/collaboration-execution.md`
- no rule in `skills/meta/collaboration-runtime/` is bypassed

## Files

- `collaboration-runtime-benchmark.md` — the 4 benchmark cases
