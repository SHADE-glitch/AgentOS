# Router Baseline

## Baseline Date

2026-08-30

## Sample Count

58 real task executions

## Total Cases

58

## Correct Routing

53

## Wrong Routing

5

## Accuracy

91.4%

## Main Failure Pattern

RAG and distributed-system tasks were often routed to llm-engineer or backend-architect without the expected retrieval, vector-store, or consistency-support skill set.

## Rule

The router baseline must be produced from real task data, not synthetic scenarios alone.

## Evidence

The result is derived from the assessed task dataset in `runtime/datasets/raw/tasks.md`, the runtime routing review, and the failure analysis set in `runtime/feedback/failures/analyzed/`.
