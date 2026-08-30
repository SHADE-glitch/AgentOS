# Execution Flow

The end-to-end pipeline owned by the collaboration runtime:

```text
User Request
  -> Agent Orchestrator (team plan, human-approved)
  -> Task Scheduler (layer scheduling)
  -> Agent Execution (one task card per role)
  -> Handoff (structured, validated)
  -> Result Aggregation (integration report)
  -> Quality Evaluation (quality-evaluator)
  -> Runtime Logging (collaboration-execution.md)
  -> Evolution Feedback (Type E failures, pattern stats)
```

## Layer semantics

- Layers come from the team plan `Dependency Order / Execution Layers`.
- Agents in the same layer may execute in parallel.
- A layer starts only after all upstream layers complete (barrier).

## Human touchpoints

1. **Plan approval** — the orchestrator's team plan must be approved before the runtime starts.
2. **Barrier review** — at each layer boundary, the human may review completed outputs before the next layer starts.
3. **Final quality gate** — the integrated result passes `quality-evaluator` and human review before completion.

## Stage ownership

- Orchestrator: team composition, task cards, dependency order.
- Runtime: scheduling, state, handoffs, conflict routing, aggregation, logging.
- Agents: specialist execution within their task cards.
