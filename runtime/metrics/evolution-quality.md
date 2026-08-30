# Evolution Quality

This file tracks whether the Agent OS is improving as a system.

## Core metrics

- total failures
- resolved failures
- repeated failures
- router accuracy improvement
- routing error reduction
- skill conflict reduction
- proposals generated
- proposals accepted
- proposals rejected
- average proposal turnaround time

## Template

```text
Period:
Total Failures:
Resolved Failures:
Repeated Failures:
Router Accuracy:
Routing Error Reduction:
Skill Conflict Reduction:
Proposals Generated:
Proposals Accepted:
Proposals Rejected:
Average Turnaround Time:
Observations:
```

## Example

```text
Period: 2026-08-30
Total Failures: 0
Resolved Failures: 0
Repeated Failures: 0
Router Accuracy: baseline pending
Routing Error Reduction: pending
Skill Conflict Reduction: pending
Proposals Generated: 0
Proposals Accepted: 0
Proposals Rejected: 0
Average Turnaround Time: pending
Observations: system is ready to start generating and tracking proposal records
```

## Status rule

A proposal is only considered complete when:

- the failure has been recorded
- analysis and evidence are attached
- the proposal is reviewed
- the change is either approved or rejected explicitly
- the benchmark or validation method is recorded
