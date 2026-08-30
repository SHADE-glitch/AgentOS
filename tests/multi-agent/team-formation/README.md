# Team Formation Benchmark

Validates Phase 4.2 team formation: pattern matching, role selection, and conflict rules.

## How to run

1. Feed the case `## Input` to the system.
2. Compare the formed team against `## Expected`.
3. Record pass / fail with reason.

## Pass criteria

- exact team match: lead + supporting agents
- no rejected or avoided role included
- every selected role exists in `skills/meta/role-registry.md`
- exactly one lead

## Files

- `team-formation-benchmark.md` — the 3 benchmark cases
