# Phase 4: Multi-Agent Collaboration — Architecture Design

> Status: Proposed (awaiting human review and validation)
> Date: 2026-08-30
> Scope: design document only — no implementation files are created from this document until review is complete

## Summary

Phase 4 upgrades the Agent OS from "single Agent + Skill Routing" to a "multi-agent engineering team system". It adds exactly one new meta skill, `agent-orchestrator`, and upgrades the existing collaboration layer so that complex tasks flow through team formation, dependency-ordered execution, structured handoffs, result aggregation, and the existing Phase 3 quality loop. It does not modify the router, the existing SKILL.md files, or the failure pipeline semantics. Every team execution remains human-review-gated.

## Phase numbering reconciliation

This repository already contains `runtime/phase-4-readiness-gate.md` and `runtime/phase-4-follow-up.md`. Those files describe Phase 3.5/3.6 release-governance completion (benchmark-driven quality control and release governance), not multi-agent collaboration. This document defines the roadmap's next stage, **Phase 4: Multi-Agent Collaboration**.

To avoid breaking existing artifacts:

- existing `runtime/phase-4-*` files are left untouched
- new Phase 4 artifacts use distinct names (for example `runtime/phase-4-collaboration-gate.md`)
- the existing `runtime/phase-4-readiness-gate.md` still gates Phase 3 completion; a separate collaboration gate (section 11.1) gates Phase 4 completion

## 1. Phase 3 Baseline Analysis

### 1.1 Existing layers (Agent OS v1.0 operational baseline)

| Layer | Assets | Maturity signal |
| --- | --- | --- |
| Skill Layer | 18 domain/learning skills + 5 meta skills (23 total), `skills/version.json`, `skills/version-history/` | versioned, v1.0–v1.1 |
| Router Layer | `agent-router` v1.1: lead/support selection, priority rules, fallback, runtime feedback hooks | 91.4% accuracy on 58 real tasks |
| Runtime Layer | `runtime/logs/`, `runtime/metrics/`, `runtime/telemetry/`, `runtime/feedback/` | telemetry and failure intake active |
| Evaluation Layer | `quality-evaluator`: router/skill/evolution metrics, quality gate | release gate enforced |
| Evolution Layer | `evolution-engine`: failure types A–D, improvement proposals, human-in-the-loop | 5 proposals generated / 3 accepted |
| Validation Layer | `tests/` (router benchmark, scenarios), `tests/regression/`, `tests/drift-detection/`, `tests/benchmark-runner/` | no critical regression observed |
| Maintenance Layer | `runtime/maintenance/weekly-review.md`, `runtime/dashboard.md`, `runtime/versioning/` | active |

### 1.2 What already supports collaboration

- `skills/meta/collaboration-protocol/SKILL.md`: lead/support role model, structured handoff format, collaboration examples
- `runtime/logs/collaboration-history.md`: records lead, supporting agents, handoff quality, and outcome
- `agent-router` multi-skill routing (section 7): lead + support selection with priority rules
- `runtime/README.md` already defines collaboration logging as a core responsibility

### 1.3 Gaps Phase 4 closes

1. No orchestrator role — the router picks lead/support, but nothing forms the team, sequences execution, or integrates results
2. No role contract schema — role boundaries are informal prose inside each SKILL.md
3. No team formation patterns — teams are formed ad hoc per task
4. No task lifecycle state machine
5. No dependency graph / execution ordering — agents can run unordered
6. No result aggregation / conflict resolution mechanism
7. No team-level telemetry
8. No multi-agent benchmark

### 1.4 Readiness gate status

Against `runtime/phase-4-readiness-gate.md`:

- Router accuracy >= 90%: **met** (91.4%)
- 200 real tasks: in progress (58 validated)
- 10 analyzed failures: in progress (5)
- 5 successful improvements: in progress (3 accepted)
- 30 days with no critical regression: in progress
- Human review gate: active

Conclusion: the router is stable enough to support an orchestration layer on top of it. Phase 4 does not depend on full gate completion; it reuses the existing quality loop.

### 1.5 Non-goals / what stays untouched

- `agent-router` behavior and output contract
- existing SKILL.md files (no edits until roles are validated in real teams, see section 5.3)
- `evolution-engine` failure schema semantics (extended additively only, see section 9.4)
- `knowledge/` assets
- existing `runtime/phase-4-*` files

## 2. Multi-Agent Overall Architecture

### 2.1 Pipeline

```text
User Request
  -> agent-router             (unchanged; produces lead/support candidates)
  -> agent-orchestrator       (NEW meta skill; activates only for complex tasks)
       -> Team Formation      (pattern match + pruning)
       -> Dependency Graph    (sequencing + parallelism control)
       -> Task Delegation     (structured task cards via collaboration-protocol)
       -> Team Execution      (structured handoffs only)
       -> Result Aggregation  (dedupe + conflict resolution)
  -> quality-evaluator        (review + team metrics)
  -> Human Review Gate        (mandatory)
  -> Telemetry + Evolution    (collaboration events, failure Type E)
```

### 2.2 Layering rule

The orchestrator consumes the router's lead/support output. The router keeps its own contract, output format, and versioning. Orchestrator activation is a decision made after routing, never a replacement for it. Single-role routes never reach the orchestrator.

### 2.3 Orchestrator placement

`skills/meta/agent-orchestrator/` — meta layer, sibling of `agent-router`, `collaboration-protocol`, and `quality-evaluator`.

### 2.4 Agent count discipline

`agent-orchestrator` is the only new meta skill. No new domain specialists are created. The user's reference to an "evaluation-engineer" maps to the existing `quality-evaluator`. Team growth comes from better coordination of existing roles, not from more roles.

### 2.5 Design principles

- Build on Phase 3: every team execution passes through the existing quality loop
- Minimal teams: roles are added only when a deliverable or dependency justifies them
- Structured communication: no free-form agent chat
- Human-in-the-loop: team plans, conflict escalations, and release decisions are review-gated
- Phase 5 readiness: every team artifact is designed to feed personal engineering memory later

## 3. Agent Orchestrator Design

### 3.1 Future file layout (not created until design approval)

```text
skills/meta/agent-orchestrator/
├── SKILL.md
├── protocols/
│   ├── team-formation.md
│   ├── task-delegation.md
│   └── result-aggregation.md
├── templates/
│   ├── team-plan.md
│   └── final-report.md
└── role-registry.md
```

### 3.2 Identity and mission (SKILL.md outline)

- Identity: the Agent Team Orchestrator — a multi-agent team coordinator, not an execution specialist
- Mission: turn a complex request into an ordered, reviewable team execution with integrated results
- Expertise: team composition, dependency-aware sequencing, task delegation, result integration, conflict arbitration

### 3.3 Responsibilities

1. Team creation — form the minimal team from the role registry + team patterns
2. Task allocation — produce one task card per role
3. Dependency management — build the DAG and enforce ordering
4. Execution sequencing — release tasks layer by layer
5. Result integration — dedupe, resolve conflicts, produce the final report

### 3.4 Activation rules

Activate only when:

- the router output requires 3 or more roles, or
- the task spans cross-domain deliverables (for example backend + AI + frontend), or
- the user explicitly requests a full-system design or team execution

Single-role tasks bypass the orchestrator entirely. The router remains the sole dispatcher for single-role work.

### 3.5 Workflow

- Phase 1 Assess: read router output and user context; decide team vs single-role
- Phase 2 Form: match a team pattern; prune unnecessary roles; confirm the lead
- Phase 3 Sequence: build the dependency graph; verify no cycles
- Phase 4 Delegate: emit task cards; enforce one owner per task
- Phase 5 Integrate: aggregate results; resolve conflicts; produce the final report
- Phase 6 Review: route the final report through `quality-evaluator` and the human gate

### 3.6 Engineering rules

Must:

- keep teams minimal and justified
- sequence by dependency, never unordered parallelism
- require human review of every team plan before execution
- record every team execution in telemetry

Must not:

- form a team for single-role tasks
- add roles without a deliverable or dependency
- allow two roles to own the same task
- bypass the Phase 3 quality loop

### 3.7 Output contract

The orchestrator always produces a Team Plan (section 7.5) before execution and a Final Report (section 8.1) after integration.

## 4. Collaboration Protocol Design

### 4.1 Upgrade strategy

`skills/meta/collaboration-protocol` is upgraded additively: existing sections (identity, mission, lead/support model, handoff format, workflow, examples, output contract) are preserved. New sections are appended. No deletion, no rewrite.

Appended sections:

- Structured Task Card (4.2)
- Task Lifecycle (4.3)
- Communication Rules (4.4)

### 4.2 Structured task card

Every delegated task uses one card:

```yaml
task: <unique id + short name>
owner: <single role>
input: <explicit upstream artifacts this role consumes>
expected_output: <artifact this role must produce>
status: <Created | Assigned | Executing | Reviewing | Integrated | Completed | Blocked>
result: <filled on completion; reference to the output location>
```

### 4.3 Task lifecycle

```text
Created -> Planning -> Assigned -> Executing -> Reviewing -> Integrated -> Completed
                                  \-> Blocked -> (re-plan) -> Assigned
                                  \-> Rejected (terminal; recorded as a failure)
```

Transitions are triggered only by the orchestrator (planning, assignment, integration) or by the human gate (approval, rejection).

### 4.4 Communication rules

- No free-form agent chat. All inter-agent communication is structured handoffs.
- One owner per task card at any time.
- Every handoff uses the existing handoff format and is recorded.
- Blocked tasks are reported to the orchestrator, never to other agents.

## 5. Agent Role Contract + Central Registry

### 5.1 Contract schema

```yaml
agent: <skill name>
role: <one-line role title>
responsibility: <scope this role owns>
input: <upstream artifacts required before execution>
output: <artifact this role produces>
dependencies: <upstream roles that must complete first>
consumers: <downstream roles that require this role's output>
success_criteria: <measurable conditions for accepting this role's output>
```

### 5.2 Field semantics

- `dependencies` = upstream roles whose output must exist before this role executes
- `consumers` = downstream roles that require this role's output
- The user's example ("system-architect: Depends: Backend Architect, Database Engineer") is interpreted as: system-architect has no upstream dependencies, and its consumers are `backend-architect` and `database-engineer`. This matches the real flow — the architecture proposal comes first, then domain design.

### 5.3 Registry policy (decided)

- One central registry file: `skills/meta/agent-orchestrator/role-registry.md` — the initial source of truth, generated from the existing 23 SKILL.md files
- No edits to existing SKILL.md files in Phase 4.1
- Role Contracts are embedded into individual SKILL.md files incrementally, only after a role is validated through real multi-agent collaboration scenarios

### 5.4 Example contracts

```yaml
agent: system-architect
role: System Design
responsibility: Own the system-level architecture direction
input: Business Requirements
output: Architecture Proposal
dependencies: []
consumers: [backend-architect, database-engineer, frontend-architect, llm-engineer]
success_criteria: proposal covers service boundaries, data flow, key risks, and acceptance criteria

agent: backend-architect
role: Backend Design
responsibility: Own service decomposition and API contracts
input: Architecture Proposal
output: Service Design
dependencies: [system-architect]
consumers: [database-engineer, code-reviewer]
success_criteria: service boundaries and API contracts are explicit and consistent

agent: database-engineer
role: Data Design
responsibility: Own data model, cache strategy, and consistency decisions
input: Architecture Proposal, Service Design
output: Data Model
dependencies: [system-architect, backend-architect]
consumers: [code-reviewer]
success_criteria: schema, cache strategy, and consistency decisions are defined
```

## 6. Team Formation Mechanism

### 6.1 Future directory

```text
memory/agent-team-patterns/
├── README.md               (how patterns are stored, matched, and evolved)
├── backend-project.md
├── ai-application.md
└── full-stack-product.md
```

### 6.2 Patterns

`backend-project.md`:

```text
system-architect
  -> backend-architect
  -> database-engineer
  -> distributed-system
  -> testing-engineer
  -> devops-engineer
  -> code-reviewer
```

`ai-application.md`:

```text
system-architect
  -> llm-engineer
  -> rag-engineer
  -> backend-architect
  -> quality-evaluator
```

The user's "evaluation-engineer" maps to the existing `quality-evaluator`. No new role is created.

`full-stack-product.md` (derived from the user's AI商城 example):

```text
system-architect
  -> backend-architect
  -> database-engineer
  -> llm-engineer
  -> frontend-architect
  -> code-reviewer
```

### 6.3 Formation algorithm

1. Match task features against pattern triggers
2. Take the nearest pattern as the baseline
3. Prune roles with no deliverable in this task
4. Confirm the lead (defaults to `system-architect` for design-first tasks)
5. Emit the team plan for human review

### 6.4 Team size rules

- Simple task: 1 role, no team, no orchestrator
- Medium task: lead + 1–2 supports
- Complex task: pattern-based team, capped at ~7 roles

### 6.5 Phase 5 hook

Each pattern file carries an effectiveness section (times used, average quality score, conflicts observed). Over time this data feeds Phase 5 personal engineering memory: which patterns suit this user's projects and preferred depth.

## 7. Dependency Graph Design

### 7.1 DAG construction

- Nodes = selected roles
- Edges = `dependencies` / `consumers` declarations from the role registry
- Pattern ordering is a default; the registry is the source of truth
- Cycle detected -> promote the lead to arbitrate and break one edge by re-scoping a role

### 7.2 Execution layers (e-commerce example)

```text
Layer 0: system-architect
Layer 1: backend-architect, database-engineer, llm-engineer, frontend-architect
Layer 2: code-reviewer
Layer 3: testing-engineer
```

### 7.3 Parallelism rules

- Roles in the same layer may run in parallel only if no consumer edge exists between them
- No role executes before all its dependencies complete
- Layer release is controlled by the orchestrator

### 7.4 Cycle handling

- Cycles are detected during team-plan construction, not at runtime
- Break rule: the lead re-scopes the conflicting role boundary and records the decision

### 7.5 Team plan embedding

Every team plan (`templates/team-plan.md`) embeds the DAG as an ASCII diagram plus the ordered task card list. Human review checks the DAG before execution.

## 8. Result Aggregation Mechanism

### 8.1 Final report template

`templates/final-report.md`:

1. Task Objective
2. Team & Roles (from the team plan)
3. Execution Summary (per-role status and key artifacts)
4. Integrated Results (deduplicated)
5. Conflict Resolutions (issue / options / decision / rationale)
6. Open Risks
7. Human Review Checklist
8. Quality Gate Status (pass / hold / fail)

### 8.2 Dedupe rules

- Identical findings from multiple roles are merged once, with attribution to all sources
- Overlapping scope is resolved by the lead; the resolution is recorded

### 8.3 Conflict resolution rules

- Same-layer conflicts: the lead decides with rationale
- Cross-layer conflicts: re-check the dependency graph; fix ordering first
- Unresolvable conflicts: escalate to the user (human-in-the-loop)
- Every conflict is recorded in the final report and in `runtime/logs/collaboration-history.md`

### 8.4 Integration quality checks

Before review:

- no duplicate claims
- no contradictory decisions without a resolution record
- every `expected_output` delivered
- every task card completed or explicitly Blocked / Rejected

## 9. Runtime Integration Plan

### 9.1 Telemetry

New event category: `runtime/telemetry/collaboration-events.md` alongside the existing task/routing/skill/evolution events.

Event fields:

```yaml
task_id:
pattern_used:
agents_used:
execution_order:
dependency_violations:
conflicts:
final_quality:
```

### 9.2 Log format upgrade

`runtime/logs/collaboration-history.md` gains the user-specified fields:

```yaml
task:
agents_used:
execution_order:
conflicts:
final_quality:
```

Existing records are preserved; new records use the extended format.

### 9.3 Quality evaluator

Add team metrics via a new file `skills/meta/quality-evaluator/metrics/collaboration-quality.md` plus an additive metrics entry in the SKILL.md:

- team formation accuracy
- dependency violation rate
- conflict count per task
- integration quality (dedupe and resolution completeness)

### 9.4 Evolution engine

Extend the failure schema additively with error **Type E = Coordination Failure**:

- dependency violation
- role overlap / boundary conflict
- unresolved integration conflict
- missing team role

Collaboration failures flow into the existing `runtime/feedback/failures/` pipeline unchanged. The existing automation rule (same failure >= 3 times -> improvement proposal) applies to Type E exactly as to Types A–D.

### 9.5 Full loop

```text
Task
  -> team execution
  -> collaboration telemetry
  -> quality evaluator (team metrics)
  -> regression detection
  -> evolution (Type E analysis)
  -> improvement proposal
  -> human review
  -> version release
```

## 10. Multi-Agent Benchmark Plan

### 10.1 Future directory

```text
tests/multi-agent/
├── README.md
├── team-formation-tests.md
└── conflict-handling-tests.md
```

### 10.2 Test groups

Test 1 — complex backend project design:

- Expected team: `system-architect` (lead) + `backend-architect`, `database-engineer`, `distributed-system`, `code-reviewer`
- Checks: correct team, correct lead, no missing role, no unnecessary role

Test 2 — AI application design:

- Expected team includes `llm-engineer` and `rag-engineer`
- Must NOT contain a phantom evaluation-engineer (maps to `quality-evaluator`)

Test 3 — agent conflict handling:

- Two roles produce conflicting proposals
- Check: the aggregation protocol resolves the conflict via lead decision or human escalation, and the resolution is recorded

Negative cases:

- a simple single-domain task must NOT form a team
- dependency order must not be violated (no role before its upstream)
- duplicate-ownership task cards must be rejected

### 10.3 Pass criteria

Each test records pass / fail / hold with expected vs actual team, execution order, and conflict resolution records. A passing suite requires all positive tests to pass and all negative cases to be correctly rejected.

### 10.4 Benchmark runner registration

`tests/benchmark-runner/README.md` gets an additive reference registering the multi-agent suite as an additional suite. Existing suites are untouched.

## 11. Phase 4 Acceptance Criteria + Implementation Roadmap

### 11.1 Acceptance gate

New future file `runtime/phase-4-collaboration-gate.md` with criteria:

- team formation benchmark accuracy >= 90%
- zero dependency violations in recorded executions
- every multi-agent task emits collaboration telemetry
- all conflicts resolved and recorded
- multi-agent results pass review + benchmark
- collaboration failures enter the failure system
- human review gate remains mandatory for team plans, conflicts, and releases

### 11.2 Incremental implementation roadmap (after design review)

- M1: `agent-orchestrator` SKILL.md + role registry (design sections 3, 5)
- M2: `collaboration-protocol` upgrade + `memory/agent-team-patterns/` (sections 4, 6)
- M3: runtime integration — telemetry, log format, quality metrics, failure Type E (section 9)
- M4: `tests/multi-agent/` benchmark suite (section 10)
- M5: `runtime/phase-4-collaboration-gate.md` + `skills/version.json` / `skills/version-history/` entries for `agent-orchestrator` + root README update

Each milestone is independently reviewable and must pass the existing quality gate before the next one begins.

### 11.3 Human-in-the-loop policy

- team plan: human approves before execution
- conflict escalation: human decides when the lead cannot
- quality gate: human review remains mandatory for every release decision

### 11.4 Phase 5 preparation

- team patterns carry effectiveness stats (section 6.5)
- team-plan and final-report artifacts are stored under `memory/` for later personalization
- collaboration telemetry provides the data Phase 5 needs to build a Personal Engineering Profile

## References

- `runtime/phase-4-readiness-gate.md` — Phase 3 completion gate
- `runtime/phase-4-follow-up.md` — Phase 3.5/3.6 release-governance completion
- `skills/meta/agent-router/SKILL.md` — routing layer
- `skills/meta/collaboration-protocol/SKILL.md` — protocol to upgrade
- `skills/meta/quality-evaluator/SKILL.md` — evaluation layer
- `skills/meta/evolution-engine/SKILL.md` — evolution layer
- `runtime/logs/collaboration-history.md` — collaboration log to extend
- `runtime/telemetry/README.md` — telemetry categories
- `runtime/dashboard.md` — current operational baseline
- `memory/skill-routing-matrix.md` — routing reference
- `tests/benchmark-runner/README.md` — benchmark runner
