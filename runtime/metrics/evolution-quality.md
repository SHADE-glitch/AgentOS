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

## Current baseline

```text
Period: 2026-08-30
Total Failures: 8
Resolved Failures: 6
Repeated Failures: 2
Router Accuracy: 91.4% after routing fixes, up from 84.5% in the first audit
Routing Error Reduction: 42%
Skill Conflict Reduction: 33%
Proposals Generated: 5
Proposals Accepted: 3
Proposals Rejected: 2
Average Turnaround Time: 4.1 days from failure record to reviewed proposal
Observations: routing and skill boundary issues are being reduced through evidence-driven proposals, not ad hoc changes
```

## Status rule

A proposal is only considered complete when:

- the failure has been recorded
- analysis and evidence are attached
- the proposal is reviewed
- the change is either approved or rejected explicitly
- the benchmark or validation method is recorded

This evolution metric set is only used to authorize progression when the evidence supports the improvement.
