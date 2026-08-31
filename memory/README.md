# Agent OS Engineering Memory System

**Phase 5 — Engineering Memory**
**Schema version**: 1.0
**Status**: active

---

## Purpose

This directory stores the system's engineering memory — accumulated experience from task execution, team formation, quality evaluation, and decision-making. It enables the system to learn from past execution rather than starting from scratch each time.

## Memory vs Knowledge

| | Memory | Knowledge |
|---|--------|-----------|
| What | What happened, what worked, what failed | Technical facts, concepts, patterns |
| Source | Execution results, observations | Domain expertise, documentation |
| Changes | Accumulates with each execution | Stable, changes with domain evolution |
| Example | "security role should join before API contract freeze" | "OAuth 2.0 authorization code flow" |

---

## Directory Structure

```
memory/
├── README.md                    ← this file
├── memory-gates.md              ← M1-M6 quality gates
├── user/
│   └── engineering-profile.md   ← user skills, preferences, learning goals
├── tasks/
│   ├── examples/                ← reference task structure examples
│   ├── architecture/            ← architecture task memories
│   ├── backend/                 ← backend task memories
│   ├── ai/                      ← AI task memories
│   ├── frontend/                ← frontend task memories
│   └── optimization/            ← optimization task memories
├── decisions/                   ← recorded decisions and their rationale
├── failures/                    ← failure analysis (symptom → root cause → prevention)
├── successes/                   ← what worked and why
├── patterns/                    ← repeatedly observed effective behaviors
├── anti-patterns/               ← repeatedly observed harmful behaviors
├── effectiveness/               ← per-skill/agent/pattern effectiveness tracking
└── hypothesis/                  ← proposed rules/patterns awaiting validation
```

---

## Memory Schema

Every memory entry MUST include this metadata block:

```yaml
memory_id: <unique-id>
type: <task|decision|success|failure|pattern|anti-pattern|effectiveness|user-profile|hypothesis>
created_at: <ISO-8601>
source:
  type: <benchmark|real-project|observation|hypothesis>
  task_id: <round0-task-id>      # if from benchmark
  run_id: <round0>               # if from benchmark
  mode: <single|multi>           # if from benchmark
category: <architecture|backend|ai|frontend|optimization|cross-cutting>
confidence: <low|medium|high>
evidence_level: <hypothesis|benchmark_evaluated|independent_validated|real_project_validated|production_validated>
tags: [<relevant-tags>]
status: <new|observed|validated|trusted|deprecated>
```

---

## Memory Types

| type | purpose | stores |
|------|---------|--------|
| `task` | Record of an executed task (context, agents, results, quality) | `memory/tasks/` |
| `decision` | Why a specific technical or process choice was made | `memory/decisions/` |
| `success` | What worked, why it worked, whether it can be generalized | `memory/successes/` |
| `failure` | What failed, root cause, impact, correction, prevention | `memory/failures/` |
| `pattern` | Repeatedly observed effective behavior across tasks | `memory/patterns/` |
| `anti-pattern` | Repeatedly observed harmful behavior or team inflation | `memory/anti-patterns/` |
| `effectiveness` | Per-skill/agent/team-pattern observed effectiveness | `memory/effectiveness/` |
| `user-profile` | User engineering profile for personalization | `memory/user/` |
| `hypothesis` | Proposed rule/pattern awaiting validation | `memory/hypothesis/` |

---

## Memory Lifecycle

```text
new          ← just created, no evidence yet
  ↓
observed     ← at least 1 observation recorded
  ↓
validated    ← confirmed by multiple independent observations
  ↓
trusted      ← repeatedly validated, no contradictions
  ↓
deprecated   ← evidence contradicts or pattern is no longer relevant
```

---

## Evidence Level

Memories must be tagged with the highest evidence level they have actually achieved:

| level | meaning | minimum confidence |
|-------|---------|-------------------|
| `hypothesis` | Proposed, untested | low |
| `benchmark_evaluated` | Observed in benchmark execution | medium |
| `independent_validated` | Confirmed by multiple independent benchmarks | medium-high |
| `real_project_validated` | Confirmed in real (non-production) project | high |
| `production_validated` | Confirmed in real production system | high |

**Rule**: Evidence level must never be overclaimed. A memory from Round 0 benchmark is `benchmark_evaluated`, not `real_project_validated`.

---

## Memory Retrieval

When an agent needs to retrieve memory for a task:

1. Classify the task (category, domains, complexity)
2. Query memory by type + category + tags
3. Filter by evidence_level (higher priority first)
4. Exclude `status: deprecated`
5. Inject only relevant memories into agent context

**Never** inject the entire memory directory into a prompt.

---

## Quality Gates

All memories must pass the M1-M6 quality gates before promotion. See `memory/memory-gates.md` for details:

- M1: Provenance (every memory has a source)
- M2: Evidence Level (declared, not overstated)
- M3: Duplicate Detection (no redundant entries)
- M4: Confidence (justified by observation count)
- M5: Retrieval Relevance (filtered, not dumped)
- M6: Staleness (deprecated/stale excluded)

---

## Consumer Modules

| module | consumes | purpose |
|--------|----------|---------|
| `agent-router` | `skill-routing-matrix.md` | routing decision reference |
| `agent-orchestrator` | `patterns/` | team formation pattern matching |
| `collaboration-runtime` | `patterns/` | dependency_order cross-check, effectiveness feedback |
| `role-registry` | `skill-routing-matrix.md` | lead/support role signals |

---

## Rules

1. Round 0 historical data is immutable. Do not modify past scores, winners, or rules.
2. `cost_delta ≤ 2` is a hypothesis, not a rule change. Store in `memory/hypothesis/`.
3. Memory does NOT automatically modify Skills. That is Phase 7 Evolution.
4. Hypothesis ≠ Fact. All "should do X" statements must be in `hypothesis/`.
5. Confidence must be justified by observation count, not intuition.
6. Evidence level must never be overclaimed.

---

*Schema version 1.0 | Phase 5 Engineering Memory | 2026-08-30*