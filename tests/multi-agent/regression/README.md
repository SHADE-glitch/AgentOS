# Multi-Agent Regression Tests

Regression protection for the multi-agent layer: team formation, collaboration, and quality.

## When to run

Before any release that touches the multi-agent layer (orchestrator, runtime, patterns, roles, protocol) — and after every benchmark round.

## Procedure

1. Re-run the Phase 4.2 team-formation benchmark (`../team-formation/team-formation-benchmark.md`).
2. Re-run the Phase 4.3 collaboration-runtime benchmark (`../collaboration-runtime/collaboration-runtime-benchmark.md`).
3. Compare Type E failure counts and quality metrics against `regression-gates.md` baselines.
4. Record results in `regression-gates.md`.

## Gates

- G1 Team formation: formation benchmark pass rate must stay 3/3.
- G2 Collaboration failure: Type E failure count per round must not increase vs baseline.
- G3 Quality: multi-agent mean quality_score and single-vs-multi delta must not drop below the previous comparison report.

Any gate failure blocks the release and creates an evolution-engine improvement proposal.
