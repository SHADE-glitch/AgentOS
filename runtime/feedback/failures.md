# Failure Data Model

This file is a lightweight pointer to the canonical failure record system under `runtime/feedback/failures/`.

## Canonical storage

- `runtime/feedback/failures/pending/`
- `runtime/feedback/failures/analyzed/`
- `runtime/feedback/failures/resolved/`
- `runtime/feedback/failures/templates/failure-template.yaml`

## Required schema

```yaml
failure_id: F-000
created_at: 2026-08-30T00:00:00Z
task: "Short description of the task that failed"
user_intent: "Architecture / Coding / Debug / Review / Optimization / Learning / Research"
selected_skill: "actual_skill_used"
expected_skill: "expected_primary_skill"
supporting_skills:
  - "supporting_skill_a"
  - "supporting_skill_b"
error_type: "A"
# A = Wrong Lead Skill
# B = Missing Support Skill
# C = Skill Boundary Conflict
# D = Fallback Failure
root_cause: "Why the system selected the wrong route or missed a required skill"
impact: "Impact on task quality, runtime, or user trust"
frequency: 1
recommended_fix: "Specific route rule, skill boundary, or prompt change"
verification_method: "Benchmark or validation plan required to verify the fix"
status: "pending"
```

## Lifecycle

```text
pending -> analyzed -> resolved
```

## Important rule

Failures are not blame records. They are input to the improvement pipeline.
