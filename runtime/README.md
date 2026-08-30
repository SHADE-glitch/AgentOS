# Runtime Observation Layer

This directory is the execution and feedback layer of the Agent OS.

Its goal is simple:

- capture what the agent actually did
- measure routing quality
- record failures and learning signals
- provide improvement candidates for the skill system

## Scope

The runtime layer is intentionally small and operational.

It does not replace `skills`, `knowledge`, or `memory`.
It complements them by giving the system evidence.

## Core responsibilities

1. Route logging
   - which task was assigned to which lead skill
   - whether supporting skills were used
   - whether the route was correct

2. Execution logging
   - which skill performed the work
   - what result was produced
   - what quality level was observed

3. Collaboration logging
   - which lead/support agents participated
   - whether handoff was clear
   - whether the collaboration was effective

4. Metrics tracking
   - route accuracy
   - skill usage frequency
   - failure counts
   - learning progress

5. Failure feedback
   - route errors
   - skill misfires
   - missing support roles
   - repeated problem patterns

## Runtime loop

Task execution
  -> record task outcome
  -> analyze quality and failures
  -> update metrics and feedback
  -> feed improvements back to `agent-evolution-engineer`
  -> tune routing and prompts

## Standard task record

Every major task should leave a record in the runtime log using this format:

```text
Date:
Task:
User Intent:
Selected Lead Skill:
Supporting Skills:
Execution Result:
Quality: Excellent / Good / Needs Improvement
Problem:
Improvement Suggestion:
```

## Important rule

The runtime layer exists to make the Agent OS observable.
It should never become a place for unused theory or decorative documents.
Only records with real value should be retained.
