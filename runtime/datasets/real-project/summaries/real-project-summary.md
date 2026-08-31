# Real Project Summary Dashboard

## Purpose

Long-term cumulative tracking of real project validation metrics.

---

## Current State

```yaml
projects: 1
real_projects:
  PROJ-001:
    executions: 4 (1 success, 3 timeout)
    completed_tasks: 1
    pending_tasks: 4
    memory_used: 5 per execution
    memory_influence: confirmation
    evidence_level: real_project_candidate
```

---

## Metrics (Phase 5.9.2 — Pilot Execution)

| Metric | Value |
|--------|-------|
| task_success | 1 |
| task_failed | 3 (all timeout) |
| memory_use | 5 per execution |
| memory_influence | confirmation |
| memory_helpful | 0 (runtime not reached) |
| memory_harmful | 0 |
| memory_misapplication | 0 |
| rework | 0 |
| human_feedback | 0 |

---

## Project List

| ID | Name | Tasks | Executions | Completed | Status |
|----|------|-------|------------|-----------|--------|
| PROJ-001 | aiview | 5 | 4 | 1 | runtime_recovered (mimo-v2.5-free) |

---

## Runtime Status

```yaml
opencode_version: 1.18.25
status: RECOVERED
working_model: opencode/mimo-v2.5-free
reason: |
  Switched default model to mimo-v2.5-free (Phase 5.9.2.2).
  Previous 3 free models (ling, big-pickle, nemotron) remain provider-timeout.
memory_retrieval: FUNCTIONAL
feedback_collector: FUNCTIONAL
feedback_collector_idempotent: CONFIRMED
```

---

## Status

```yaml
phase: 5.9.2
status: REAL_PROJECT_PILOT: PARTIAL
real_project_evidence: insufficient
runtime_available: false
projects_onboarded: 1
```