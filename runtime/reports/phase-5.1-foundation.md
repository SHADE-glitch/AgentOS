# Phase 5.1 — Memory Foundation Report

**Date**: 2026-08-30
**Status**: COMPLETED
**Phase**: 5.1 (Foundation — Inventory, Schema, Migration Plan)

---

## 1. Current Memory Inventory

### 1.1 File Inventory

| # | file | type | has_consumer | content_summary |
|---|------|------|-------------|-----------------|
| 1 | `memory/README.md` | meta | no | Basic memory-vs-knowledge distinction (7 lines, outdated) |
| 2 | `memory/agent-improvements.md` | log | no | Runtime summary of improvements, 4 improvement rules |
| 3 | `memory/project-history.md` | reference | no | One example project (Java+AI platform), lifecycle model |
| 4 | `memory/project-life-cycle.md` | reference | no | Phase 1-4 project lifecycle (start→dev→problems→end) |
| 5 | `memory/skill-routing-matrix.md` | **active** | **yes** | 20 routing rules with lead/support/confidence/fallback |
| 6 | `memory/user-learning-profile.md` | profile | no | User strengths, weak areas, learning goals, strategy |
| 7 | `memory/agent-team-patterns/` | **active** | **yes** | 6 team formation patterns, schema, lifecycle policy |
| 8 | `memory/patterns/` | **duplicate** | **no** | Identical copy of `agent-team-patterns/` (6 files, same content) |

### 1.2 Consumer Map

| consumer file | references | dependency |
|---------------|-----------|------------|
| `skills/meta/agent-router/SKILL.md` | `memory/skill-routing-matrix.md` | **HARD** — routing decisions depend on matrix |
| `skills/meta/role-registry.md` | `memory/skill-routing-matrix.md` | **HARD** — lead/support signals from matrix |
| `skills/meta/agent-orchestrator/SKILL.md` | `memory/agent-team-patterns/` | **HARD** — pattern matching for team formation |
| `skills/meta/agent-orchestrator/templates/team-plan.md` | `memory/agent-team-patterns/` | **HARD** — `matched_from` field |
| `skills/meta/collaboration-runtime/SKILL.md` | `memory/agent-team-patterns/` | **HARD** — `dependency_order` cross-check, failure recording |
| `runtime/logs/team-formation-history.md` | `memory/agent-team-patterns/` | **SOFT** — log reference |
| `runtime/reports/phase-4-final-report.md` | `memory/tasks/`, `memory/failures/`, etc. | **FUTURE** — Phase 5 plan references |

### 1.3 Duplication Analysis

```
memory/agent-team-patterns/    memory/patterns/
├── README.md                  ├── README.md            (IDENTICAL)
├── ai-application.md          ├── ai-application.md    (IDENTICAL)
├── architecture-review.md     ├── architecture-review.md   (IDENTICAL)
├── backend-project.md         ├── backend-project.md   (IDENTICAL)
├── full-stack-product.md      ├── full-stack-product.md    (IDENTICAL)
└── system-optimization.md     └── system-optimization.md   (IDENTICAL)
```

- `patterns/` is a complete copy of `agent-team-patterns/`
- Only `agent-team-patterns/` is consumed by running modules
- `patterns/` has zero consumers
- **Decision: DELETE `patterns/` entirely**

---

## 2. Per-File Decision: keep / merge / migrate / deprecate

### 2.1 `memory/README.md`

| property | value |
|----------|-------|
| current role | Basic memory-vs-knowledge description |
| consumer count | 0 |
| decision | **REWRITE** — replace with Phase 5 Memory Schema |

Current content is 7 lines. Will be replaced with:
- Memory schema definition
- Memory types and their purposes
- Memory lifecycle (new→observed→validated→trusted→deprecated)
- Memory quality gates reference
- Consumer integration guide

### 2.2 `memory/agent-improvements.md`

| property | value |
|----------|-------|
| current role | Runtime summary log of improvements |
| consumer count | 0 |
| information type | Historical changelog (not structured memory) |
| decision | **MIGRATE** — extract decisions to `memory/decisions/`, deprecate original |

Content:
- "Added a runtime validation directory" → `decisions/runtime-validation.md`
- "Added routing matrix and skill-version tracking" → `decisions/routing-matrix.md`
- "Added collaboration protocol" → `decisions/collaboration-protocol.md`
- "Added a project lifecycle model" → `decisions/project-lifecycle.md`
- 4 improvement rules → `patterns/improvement-rules.md` or `decisions/improvement-rules.md`

### 2.3 `memory/project-history.md`

| property | value |
|----------|-------|
| current role | One example project record |
| consumer count | 0 |
| information type | Reference example (not real task execution data) |
| decision | **KEEP** — but move to `memory/tasks/examples/` as reference |

Content is a single example (Java+AI platform). Not a real executed task. Keep as a template/example for future task memory entries.

### 2.4 `memory/project-life-cycle.md`

| property | value |
|----------|-------|
| current role | Generic Phase 1-4 lifecycle model |
| consumer count | 0 |
| information type | Reference workflow |
| decision | **KEEP** — move to `memory/patterns/project-lifecycle.md` |

This is a reusable workflow pattern, not a task memory. Fits under `patterns/`.

### 2.5 `memory/skill-routing-matrix.md`

| property | value |
|----------|-------|
| current role | Active routing reference for agent-router |
| consumer count | 2 (agent-router, role-registry) |
| information type | Knowledge asset (routing rules) |
| decision | **KEEP AS-IS** — no migration needed |

This file has HARD dependencies. Any path change would break the router. It functions as a knowledge asset, not a memory in the Phase 5 sense. It should remain at its current location.

**Note**: The confidence values (0.86-0.97) are not benchmark-validated. They should be marked as `INSUFFICIENT EVIDENCE` for accuracy claims. This is a Phase 6 concern.

### 2.6 `memory/user-learning-profile.md`

| property | value |
|----------|-------|
| current role | User learning profile |
| consumer count | 0 |
| information type | User profile |
| decision | **MIGRATE** → `memory/user/engineering-profile.md` |

Per `text.txt` section suggestion. Content is already close to the desired format. Needs:
- Explicit technical skill levels (Java: Intermediate, etc.)
- Added `text.txt` section 十一 fields (技术能力, 学习偏好)
- Keep existing content as base

### 2.7 `memory/agent-team-patterns/`

| property | value |
|----------|-------|
| current role | Active team formation pattern library |
| consumer count | 4 (agent-orchestrator, collaboration-runtime, team-plan, team-formation-history) |
| information type | Pattern memory (with schema) |
| decision | **KEEP** — but merge into unified `memory/patterns/` |

The `agent-team-patterns/README.md` already defines a good schema, matching procedure, and evolution policy. This is the foundation for Phase 5 pattern memory.

**Migration plan**:
1. DELETE `memory/patterns/` (the duplicate)
2. MOVE `memory/agent-team-patterns/` → `memory/patterns/`
3. UPDATE all 4 consumer references from `memory/agent-team-patterns/` to `memory/patterns/`

### 2.8 `memory/patterns/` (duplicate)

| property | value |
|----------|-------|
| current role | Exact duplicate of agent-team-patterns |
| consumer count | 0 |
| decision | **DELETE** — entirely redundant |

---

## 3. Migration Summary

```text
DELETE:
  memory/patterns/                          (6 files, duplicate)

REWRITE:
  memory/README.md                          (→ Phase 5 Memory Schema)

MIGRATE:
  memory/agent-improvements.md              → memory/decisions/ (4 files)
  memory/user-learning-profile.md           → memory/user/engineering-profile.md
  memory/agent-team-patterns/               → memory/patterns/ (MOVE)
  memory/project-history.md                 → memory/tasks/examples/
  memory/project-life-cycle.md              → memory/patterns/project-lifecycle.md

KEEP AS-IS:
  memory/skill-routing-matrix.md            (HARD dependency, knowledge asset)

CREATE NEW:
  memory/decisions/                         (from agent-improvements.md)
  memory/user/engineering-profile.md        (from user-learning-profile.md)
  memory/tasks/examples/                    (from project-history.md)
  memory/patterns/project-lifecycle.md      (from project-life-cycle.md)
  memory/memory-gates.md                    (M1-M6 quality gates)
  memory/failures/                          (empty, populate in Phase 5.2)
  memory/successes/                         (empty, populate in Phase 5.2)
  memory/anti-patterns/                     (empty, populate in Phase 5.2)
  memory/effectiveness/                     (empty, populate in Phase 5.2)
  memory/hypothesis/                        (empty, populate in Phase 5.2)
```

---

## 4. Phase 5 Memory Schema

### 4.1 Unified Metadata Block

Every memory entry MUST include:

```yaml
memory_id: <unique-id>
type: <task|decision|success|failure|pattern|anti-pattern|effectiveness|user-profile|hypothesis>
created_at: <ISO-8601>
source:
  type: <benchmark|real-project|observation|hypothesis>
  task_id: <round0-task-id>      # if from benchmark
  run_id: <round0>               # if from benchmark
  mode: <single|multi>           # if from benchmark
category: <architecture|backend|ai|frontend|optimization>
confidence: <low|medium|high>
evidence_level: <benchmark_evaluated|real_project_validated|production_validated|hypothesis>
tags: [<relevant-tags>]
status: <new|observed|validated|trusted|deprecated>
```

### 4.2 Memory Types

| type | purpose | example |
|------|---------|---------|
| `task` | Record of an executed task (context, agents, results) | backend-02 payment system |
| `decision` | Why a specific technical or process choice was made | cost_delta threshold choice |
| `success` | What worked and why | cross-domain multi-agent collaboration |
| `failure` | What failed, root cause, prevention | security role too late in team formation |
| `pattern` | Repeatedly observed effective behavior | 3+ domain complex task → multi-agent |
| `anti-pattern` | Repeatedly observed harmful behavior | single-domain → unnecessary team |
| `effectiveness` | Per-skill/agent/pattern success tracking | database-engineer observations |
| `user-profile` | User engineering profile for personalization | tech stack, learning preferences |
| `hypothesis` | Proposed rule/pattern awaiting validation | cost_delta ≤ 2 threshold |

### 4.3 Memory Lifecycle

```text
new          ← just created, no evidence yet
  ↓
observed     ← at least 1 observation
  ↓
validated    ← confirmed by multiple independent observations
  ↓
trusted      ← repeatedly validated, no contradictions
  ↓
deprecated   ← evidence contradicts or pattern is no longer relevant
```

### 4.4 Evidence Level Hierarchy

| level | meaning | confidence |
|-------|---------|------------|
| `production_validated` | Confirmed in real production system | high |
| `real_project_validated` | Confirmed in real (non-production) project | high |
| `independent_validated` | Confirmed by multiple independent benchmarks | medium-high |
| `benchmark_evaluated` | Observed in benchmark execution | medium |
| `hypothesis` | Proposed, untested | low |

---

## 5. Consumer Reference Update Plan

When `agent-team-patterns/` is moved to `patterns/`, these files must be updated:

| file | old reference | new reference |
|------|--------------|---------------|
| `skills/meta/agent-orchestrator/SKILL.md` (line 55) | `memory/agent-team-patterns/` | `memory/patterns/` |
| `skills/meta/agent-orchestrator/SKILL.md` (line 145) | `memory/agent-team-patterns/` | `memory/patterns/` |
| `skills/meta/collaboration-runtime/SKILL.md` (line 54) | `memory/agent-team-patterns/` | `memory/patterns/` |
| `skills/meta/collaboration-runtime/SKILL.md` (line 90) | `memory/agent-team-patterns/` | `memory/patterns/` |
| `skills/meta/agent-orchestrator/templates/team-plan.md` (line 13) | `memory/agent-team-patterns/` | `memory/patterns/` |
| `skills/version-history/agent-orchestrator/v1.1.md` (line 5) | `memory/agent-team-patterns/` | `memory/patterns/` |
| `runtime/logs/team-formation-history.md` (line 19) | `memory/agent-team-patterns/` | `memory/patterns/` |

---

## 6. Memory Quality Gates (M1-M6)

### M1: Provenance Gate

Every memory MUST have a `source` block with at minimum:
- `type` (benchmark|real-project|observation|hypothesis)
- For benchmark: `task_id`, `run_id`

**Fail**: Missing source → memory cannot enter `validated` status.

### M2: Evidence Level Gate

Every memory MUST declare an `evidence_level`. Default is `hypothesis` if no evidence exists.

**Fail**: Missing evidence_level → memory cannot be used for routing or orchestration decisions.

### M3: Duplicate Detection Gate

Before creating a new memory, check for existing memories with:
- Same `type` + same `category` + similar content

**Fail**: Duplicate found → merge or reject, do not create a new entry.

### M4: Confidence Gate

Confidence must be justified by evidence count:
- `low`: 0-1 observations
- `medium`: 2-4 observations
- `high`: 5+ independent observations

**Fail**: `high` confidence with < 5 observations → downgrade to `medium`.

### M5: Retrieval Relevance Gate

Memory retrieval must filter by:
- Task category match
- Evidence level (higher priority first)
- Status (exclude deprecated)

**Fail**: No relevance filter → memory pollution risk.

### M6: Staleness Gate

Memories with `status: deprecated` or `created_at > 90 days` without re-validation must be reviewed.

**Fail**: Stale memory used in active decision → flag for review.

---

## 7. Implementation Plan (Remaining Steps)

### Phase 5.1 (current — DONE)
- [x] Inventory existing memory
- [x] Consumer map
- [x] Schema design
- [x] Migration decisions
- [x] Foundation report

### Phase 5.1 — Pending (execute next)
- [ ] Delete `memory/patterns/` (duplicate)
- [ ] Move `agent-team-patterns/` → `patterns/`
- [ ] Update 7 consumer references
- [ ] Rewrite `memory/README.md` with new schema
- [ ] Create `memory/memory-gates.md`
- [ ] Create empty directories: `failures/`, `successes/`, `anti-patterns/`, `effectiveness/`, `hypothesis/`
- [ ] Migrate `agent-improvements.md` → `decisions/`
- [ ] Migrate `user-learning-profile.md` → `user/engineering-profile.md`
- [ ] Migrate `project-history.md` → `tasks/examples/`
- [ ] Migrate `project-life-cycle.md` → `patterns/project-lifecycle.md`

### Phase 5.2 (Memory Migration)
- [ ] Create Round 0 task memories → `memory/tasks/` (10 files)
- [ ] Create failure memories → `memory/failures/` (2 files, from conflicts)
- [ ] Create success memories → `memory/successes/` (7 files, from multi-wins)
- [ ] Create pattern memories → `memory/patterns/` (from observations)
- [ ] Create anti-pattern memory → `memory/anti-patterns/` (team inflation)
- [ ] Create hypothesis memory → `memory/hypothesis/` (cost_delta ≤ 2)
- [ ] Create effectiveness baselines → `memory/effectiveness/`
- [ ] Add provenance to all memories

### Phase 5.3 (Retrieval + Integration)
- [ ] Implement Memory Retrieval Protocol
- [ ] Integrate with Router
- [ ] Integrate with Orchestrator

### Phase 5.4 (Tests + Acceptance)
- [ ] Create `tests/memory/` directory structure
- [ ] Write 6 quality gate tests
- [ ] Write 10 retrieval test cases
- [ ] Generate `phase-5-memory-report.md`

---

## 8. Known Limitations

| limitation | severity | mitigation |
|------------|----------|------------|
| Only 10 tasks — thin evidence base | medium | Phase 5.2 memories marked `evidence_level: benchmark_evaluated`, not `validated` |
| `skill-routing-matrix.md` confidence values unvalidated | medium | Mark as `INSUFFICIENT EVIDENCE`, defer to Phase 6 |
| No real production data | high | All memories capped at `benchmark_evaluated` |
| `agent-team-patterns/` effectiveness_stats all `times_used: 0` | low | Populate from Round 0 data in Phase 5.2 |
| Consumer reference updates are cross-file changes | medium | Each consumer update is a single path string change, low risk |

---

## 9. Phase 5.1 Acceptance

```text
Memory Inventory         ✅  8 files analyzed, 2 active consumers identified
Consumer Map             ✅  7 cross-references documented
Schema Design            ✅  Unified metadata, 9 types, 5 lifecycle states
Migration Decisions      ✅  2 delete, 1 rewrite, 5 migrate, 1 keep-as-is
Duplication Resolved     ✅  patterns/ identified as duplicate, deletion planned
Quality Gates Defined    ✅  M1-M6 gates defined
Implementation Plan      ✅  4 phases, ~30 steps
```

**Phase 5.1 Status: COMPLETED**

Next step: Execute the pending migration tasks (delete duplicates, move files, update consumers, create directories).

---

*Report generated: 2026-08-30 | Phase 5.1 Foundation | Evidence: codebase inspection*