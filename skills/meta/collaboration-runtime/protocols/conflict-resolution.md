# Conflict Resolution

Conflict types are scoped to team collaboration. These Types A-D are distinct from the failure `error_type` values A-D in `skills/meta/evolution-engine/SKILL.md` section 12 (which classify routing failures).

## Conflict types

- **Type A — Architecture conflict**: cross-domain design disagreement. The lead decides.
- **Type B — Implementation conflict**: competing technical approaches. The lead decides from evidence.
- **Type C — Requirement conflict**: contradictory requirements. The lead decides, human escalation required.
- **Type D — Quality conflict**: quality gate dispute. The quality-evaluator arbitrates.

## Resolution flow

```text
Agent disagreement
  -> Evidence comparison (both sides state evidence)
  -> Lead decision (recorded)
  -> Human escalation (when triggers fire)
```

## Escalation triggers

- the lead decision is contested
- the conflict is a cross-domain trade-off with product impact
- the quality gate fails or is disputed

## Recording

- Every conflict and decision is recorded in the integration report `Conflicts` and `Decisions` sections.
- An unresolved conflict becomes a Type E failure record in `runtime/feedback/failures/pending/`.
