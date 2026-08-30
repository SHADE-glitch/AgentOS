# Execution State

This directory holds the runtime execution state for multi-agent teams managed by `skills/meta/collaboration-runtime/`.

## File convention

- One state file per team, named `<team_id>.yaml`.
- The file uses the schema in `skills/meta/collaboration-runtime/templates/execution-state.yaml`.

## Lifecycle mapping

| State file location | Task statuses |
|---|---|
| `active/` | Created, Planned, Assigned, Executing, Reviewing, Integrated |
| `completed/` | Completed |
| `blocked/` | Blocked |

Files move between directories as status changes. The runtime updates `updated_at` on every transition.
