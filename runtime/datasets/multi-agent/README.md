# Multi-Agent Benchmark Dataset

This directory holds the curated benchmark dataset for the single-agent vs multi-agent comparison.

## Purpose

Answer one question with evidence: does multi-agent collaboration produce real quality gains over single-agent execution?

Relation to `runtime/datasets/raw/tasks.md`: that file stores operational task samples for router accuracy. This directory is a curated subset of team-worthy tasks, run in BOTH modes so the comparison is paired and controlled.

## Structure

```
multi-agent/
├── README.md               (this file: schemas and rules)
├── tasks/
│   ├── architecture/       (arch-01, arch-02)
│   ├── backend/            (backend-01, backend-02)
│   ├── ai/                 (ai-01, ai-02)
│   ├── frontend/           (fe-01, fe-02)
│   └── optimization/       (opt-01, opt-02)
├── single-agent-results/   (one <task_id>.yaml per task)
├── multi-agent-results/    (one <task_id>.yaml per task)
└── comparison/             (one <task_id>.yaml per task)
```

## Task schema

```yaml
task_id: <e.g. arch-01>
category: <architecture | backend | ai | frontend | optimization>
difficulty: <easy | medium | hard>
description: <real engineering task statement>
expected_roles: [<roles from skills/meta/role-registry.md>]
evaluation_points: [<what the output must cover>]
baseline_expectation: <what a competent single-agent answer covers>
multi_agent_expectation: <what a correct multi-agent team output adds>
```

## Result record schema

One file per task per mode in `single-agent-results/` or `multi-agent-results/`, named `<task_id>.yaml`:

```yaml
task_id: <id>
mode: <single | multi>
executed_roles: [<roles>]
quality_scores:
  completeness: <0-5>
  correctness: <0-5>
  architecture_quality: <0-5>
  maintainability: <0-5>
conflicts: <count>
human_review_count: <count>
notes: <observations>
```

## Sampling rule

At least 10 tasks × 2 modes = 20 result records are required before claiming a stable conclusion about single vs multi. Below that threshold, any comparison report must state "insufficient evidence".

## Special case: opt-02

`tasks/optimization/opt-02.yaml` is the team-inflation guard: a single database-engineer is the correct mode. If team formation proposes a team for it, that is recorded as a negative evidence point (conflict with Phase 4.2 rule R1).
