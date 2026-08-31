# Real Project Onboarding

## Purpose

Define how a real engineering project enters the Agent OS Memory Feedback system.

---

## Onboarding Pipeline

```
Project
  ↓   project-template.yaml
Task
  ↓   task-template.yaml
Execution
  ↓   runtime/loop-controller
Trace
  ↓   runtime/traces/
Feedback
  ↓   human review + system
```

---

## Step 1: Register Project

Create `projects/<project-id>.yaml` using the project template.

Requirements:
- Must be a real engineering project (not a benchmark, not a synthetic task)
- Must have an observable engineering outcome
- Must have a repository or work context

Forbidden:
- Fictional projects
- "Toy" examples
- Benchmark-only datasets

---

## Step 2: Define Task

For each task in the project, create `tasks/<project-id>-<task-id>.yaml` using the task template.

Requirements:
- task_description must describe the actual work done
- actual_context must be the real project context at that time
- expected_result must be defined before execution

---

## Step 3: Execute

Use the Runtime Loop Controller:

```bash
python3 runtime/loop-controller/loop_controller.py \
  <task_id> \
  "<task_description>" \
  enabled \
  opencode/big-pickle
```

For baseline:
```bash
python3 runtime/loop-controller/loop_controller.py \
  <task_id> \
  "<task_description>" \
  disabled \
  opencode/big-pickle
```

---

## Step 4: Record Trace

Traces are auto-generated in `runtime/traces/`. Do not modify them.

---

## Step 5: Collect Feedback

After execution, record human feedback:

```yaml
feedback_type: helpful | neutral | harmful | unknown
reason: "<why>"
reviewer_role: "<role>"
timestamp: "<ISO8601>"
```

Store in `feedback/<project-id>-<task-id>-feedback.yaml`.

---

## Step 6: Promotion Safety Gate

Real project evidence follows a stricter promotion path:

```
benchmark_evaluated
  → runtime_validated
  → real_project_candidate
  → human_review
  → real_project_validated
```

No automatic promotion from `runtime_validated` to `real_project_validated`.

---

## Current State

```yaml
real_project_evidence: insufficient
real_tasks_with_memory: 0
projects_onboarded: 0
status: PROVISIONAL
```