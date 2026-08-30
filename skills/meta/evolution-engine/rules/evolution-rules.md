# Evolution Rules

## Rule 1: Repeated failure triggers proposal

If the same failure pattern occurs 3 or more times, the system must generate an improvement proposal.

## Rule 2: Router degradation triggers investigation

If router accuracy or route confidence drops materially relative to the previous benchmark, trigger a router investigation.

## Rule 3: Repeated skill conflict triggers boundary review

If the same boundary conflict recurs between skills (for example backend-architect vs system-architect), trigger a boundary review and propose a clearer responsibility split.

## Rule 4: Missing support skill triggers collaboration review

If the route omits a required supporting specialty, generate a collaboration recommendation and record the failure.

## Rule 5: No silent mutation

A fix cannot be implemented without evidence, human review, and explicit benchmark validation.

## Rule 6: Improvement proposals require evidence

Every proposal must reference one or more of:

- a failure record
- a benchmark result
- a routing error classification
- system-level quality degradation

## Rule 7: Version update is mandatory for approved changes

Approved changes must be recorded in `skills/version-history` and cross-linked to the relevant failure ID or benchmark result.
