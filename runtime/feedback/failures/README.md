# Failure Data Pipeline

This directory is the canonical intake point for all runtime failures.

The pipeline is:

pending -> analyzed -> resolved

Each failure must be recorded in a structured YAML format so that the evolution engine can derive improvement proposals, benchmark validation tasks, and versioned fixes.

## Directory roles

- pending/: new failures waiting for classification
- analyzed/: failures with root-cause analysis and recommended fix
- resolved/: closed failures that were fixed and validated
- templates/: canonical schema for future failure records

## Required schema

See `templates/failure-template.yaml`.

## Exit rules

A failure should move from pending to analyzed only after:

- the task is described
- the selected skill and expected skill are recorded
- the routing or execution error is classified
- root cause is explained
- a recommendation and verification method are attached

A failure should move from analyzed to resolved only after:

- the fix has been reviewed
- the benchmark or verification step has passed
- the change is recorded in version history
