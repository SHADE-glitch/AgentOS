# Real Project Dataset

This directory stores real engineering project data for Memory Feedback evaluation.

**Not a benchmark.** This is real project evidence.

## Structure

```
real-project/
├── README.md
├── project-onboarding.md          # How to onboard a real project
├── projects/                      # Project metadata
│   └── project-template.yaml
├── tasks/                         # Task records
│   └── task-template.yaml
├── feedback/                      # Human and system feedback
│   └── feedback-template.yaml
├── summaries/                     # Aggregated metrics
│   └── real-project-summary.md
└── validation/                    # Pipeline validation (benchmark, not real project)
    ├── execution-schema.yaml
    ├── tasks/
    │   └── pilot-task-inputs.yaml
    ├── executions/
    │   └── PV-RT*.yaml
    └── comparisons/
        └── RT-*.yaml
```

## Status

```yaml
real_project_evidence: insufficient
real_tasks_with_memory: 0
projects_onboarded: 0
status: READY_FOR_REAL_PROJECT
```

## Key Distinction

| Type | Purpose | Data Source |
|------|---------|------------|
| `validation/` | Pipeline validation | Benchmark tasks (RT-001 to RT-012) |
| `projects/`, `tasks/`, `feedback/` | Real project evidence | Real engineering projects |

## Evidence Levels

| Level | Source | Confidence |
|-------|--------|------------|
| `benchmark_evaluated` | Validation pipeline | Low |
| `runtime_validated` | Runtime execution | Medium |
| `real_project_candidate` | Real project task | Medium-High |
| `real_project_validated` | Human review | High |

## Promotion Safety Gate

```
benchmark_evaluated
  → runtime_validated
  → real_project_candidate
  → human_review
  → real_project_validated
```

No automatic promotion from `runtime_validated` to `real_project_validated`.

## Privacy

All sensitive data must be redacted per `memory/real-project-feedback-protocol.md` Section 11.