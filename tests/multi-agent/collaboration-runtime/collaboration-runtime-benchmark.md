# Collaboration Runtime Benchmark Cases

Four cases validate that the collaboration runtime schedules, hands off, resolves, and aggregates correctly.

## Test 1: Dependency execution

## Input
Approved ai-application team plan:
- L0: system-architect
- L1: backend-architect, rag-engineer, database-engineer
- L2: quality-evaluator

## Expected
The runtime schedules L0 first, then L1 in parallel, then L2. quality-evaluator cannot start before L1 completes. `execution_order` in `runtime/logs/collaboration-execution.md` records the layer sequence.

## Reason
Cross-layer barrier, same-layer parallel (Dependency Scheduler rules).

## Test 2: Handoff completeness

## Input
A handoff from system-architect (L0) to backend-architect (L1) with empty `important_context`.

## Expected
The runtime rejects the contextless handoff and requests completion. A valid handoff has non-empty `completed_work`, `important_context`, `next_action`, and referenced artifacts.

## Reason
No-contextless-handoff rule in `protocols/handoff-rules.md`.

## Test 3: Conflict flow

## Input
rag-engineer and database-engineer disagree on the storage layout (vector store vs relational).

## Expected
The conflict is recorded as Type A (architecture conflict). Evidence comparison by the lead (system-architect). The lead decision is recorded in the integration report. Human escalation if the lead cannot resolve.

## Reason
Conflict resolution flow in `protocols/conflict-resolution.md`.

## Test 4: Aggregation

## Input
Three agent-result records with overlapping claims about the data model.

## Expected
The integration report Merged Result deduplicates, keeps key design decisions, and records conflicts.

## Reason
Aggregation rules in `templates/integration-report.md`.
