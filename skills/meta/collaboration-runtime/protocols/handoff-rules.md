# Handoff Rules

Every handoff uses the structured record in `skills/meta/collaboration-protocol/templates/handoff.yaml`.

## Completeness rules

- No contextless handoff: `completed_work`, `important_context`, and `next_action` must all be non-empty.
- `artifacts` must reference every produced artifact the receiver needs.
- `handoff_id` must be unique within the team.

## Recording rules

- Every handoff is recorded in `runtime/logs/collaboration-execution.md`.
- A rejected handoff is corrected and re-submitted; the rejection is recorded.

## Routing rules

- Blocked agents report to the orchestrator only, never to peer agents.
- Handoffs cross layer boundaries only after the layer barrier passes.
