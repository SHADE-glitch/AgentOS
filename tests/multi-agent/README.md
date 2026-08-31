# Multi-Agent Tests

This directory validates the multi-agent collaboration layer of the Agent OS.

## Current scope

- `phase-4.1-tests.md` — infrastructure validation: orchestrator triggering, team plan generation, and registry conformance.
- `team-formation/` — Phase 4.2 pattern matching and role selection benchmark.
- `collaboration-runtime/` — Phase 4.3 scheduling, handoff, conflict, and aggregation benchmark.
- `comparison/` — Phase 4.4 single vs multi comparison framework and report template.
- `regression/` — Phase 4.4 regression gates for formation, collaboration, and quality.

## How to run

These tests are evaluated manually against the artifacts they reference:

1. Feed the scenario `## Input` to the system.
2. Compare the produced route/plan against `## Expected`.
3. Record the result and the reason for pass/fail.

## Format

Same scenario format as `tests/router-benchmark.md`:

```text
## Input
<user request>

## Expected
<expected behavior>

## Reason
<why this is the expected behavior>
```

## Relation to the router benchmark

The router benchmark tests single-role routing. These tests validate the layer above it: when and how a team is formed. A test passes only if both the trigger decision and the team composition match the expected result.
