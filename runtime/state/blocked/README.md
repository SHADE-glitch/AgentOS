# blocked/

State files for teams that are Blocked: a task card was rejected, a conflict could not be resolved, or a handoff failed repeatedly.

A blocked team reports to the agent-orchestrator for re-planning. If re-planning succeeds, the state file moves back to `active/`; otherwise the failure is recorded as Type E in `runtime/feedback/failures/pending/`.
