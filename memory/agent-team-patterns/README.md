# Agent Team Patterns

This directory stores the team formation pattern library used by `agent-orchestrator`.

## Purpose

Each pattern answers: for a given scenario family, which team should be formed?

Patterns are memory assets, not skills. They evolve with real usage: the `effectiveness_stats` block accumulates usage data that Phase 5 personal memory will consume.

## Pattern schema

```yaml
pattern_name: <unique pattern id>
scenario: <what task family this pattern serves>
task_domains: [<domains from role-registry domain values>]
lead_role: <exactly one role from role-registry>
support_roles: [<roles from role-registry>]
optional_roles: [<roles added only when a selection rule requires them>]
dependency_order:
  - layer: 0
    roles: [<first execution layer>]
  - layer: 1
    roles: [<parallel execution layer>]
success_criteria: <what the formed team must deliver>
avoid_roles: [<roles that must never be selected for this pattern>]
effectiveness_stats:
  times_used: 0
  avg_quality_score: null
```

## Matching procedure

1. Derive task domains from the request via role-registry `activation_keywords`.
2. Score each pattern by overlap between task domains and `task_domains`.
3. The best-scoring pattern wins; ties are broken by the lead-capable domain match.

## Add-a-pattern procedure

1. Add a new `<name>.md` file with the schema block.
2. Every role name must exist in `skills/meta/role-registry.md`.
3. Add a benchmark case to `tests/multi-agent/team-formation/team-formation-benchmark.md`.
4. No changes to the orchestrator rules are needed unless a new selection rule is required.

## Evolution policy

- After each formation, update `effectiveness_stats` (times_used, avg_quality_score).
- A pattern that repeatedly produces poor teams is a candidate for an `evolution-engine` improvement proposal.
- Do not edit patterns without a recorded formation result.
