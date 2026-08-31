# Team Plan

## Task Summary
- task_id:
- objective:
- user request:

## Trigger Justification
<which activation condition fired: domain >= 2 / required_roles >= 3 / task_dependency >= 2 / explicit request>

## Pattern Used
- pattern_name:
- matched_from: `memory/patterns/<pattern>.md`

## Lead Agent
- <role> (lead) — <responsibility from role-registry>

## Supporting Agents
- <role> — <responsibility from role-registry>

## Dependency Order / Execution Layers
Layer 0:
- <role>

Layer 1:
- <role>
- <role>

Layer 2:
- <role>

## Dependencies
- <role> depends on <role> (from role-registry dependencies/consumers)

## Task Cards
- <task_id>: <role> — <objective>, expected output: <expected_output>, depends on: <task_ids>

## Risk
- <formation risk and mitigation>

## Review Plan
- <how results are reviewed: quality-evaluator for AI applications, code-reviewer for delivery, human gate always>

## Human Review Gate
- [ ] every selected role exists in `skills/meta/role-registry.md`
- [ ] no role without a deliverable
- [ ] dependency order has no cycles
- [ ] no learning or meta-maintenance role included
- [ ] exactly one lead
- [ ] rejected roles recorded with reason
- [ ] user approved before delegation
