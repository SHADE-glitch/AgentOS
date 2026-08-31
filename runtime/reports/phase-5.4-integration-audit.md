# Phase 5.4 Integration Audit

**Date**: 2026-08-30
**Status**: COMPLETE

---

## 1. Current Router Decision Flow

### 1.1 Input/Output

```yaml
router_input:
  - user_task: natural language description
  - session_context: multi-turn state, project stage, domain context

router_output:
  - lead_agent: primary specialist
  - support_agents: [optional supporting roles]
  - confidence: high | ambiguous
  - fallback_used: true | false
```

### 1.2 Decision Pipeline

```text
Step 1: Intent Detection
  (architecture, coding, debug, review, optimization, learning, research)
  ↓
Step 2: Domain Classification
  (backend, AI, frontend, architecture, engineering, devops, learning)
  ↓
Step 3: Lead Skill Selection
  (most specific specialist for primary task)
  ↓
Step 4: Supporting Skill Selection
  (only roles strictly required by task)
  ↓
Step 5: Confidence Evaluation
  (high confidence or ambiguous)
  ↓
Step 6: Fallback
  (system-architect or agent-evolution-engineer)
  ↓
Step 7: Runtime Logging
  (routing-history.md, routing-errors.md, router-metrics.md)
```

### 1.3 Current Memory Consumption

| memory source | how used | integration point |
|---------------|----------|-------------------|
| `memory/skill-routing-matrix.md` | Static reference for routing rules | Step 3 (Lead Selection) |

**Gap**: No dynamic memory retrieval. Router does not query `memory/retrieval-index.yaml` or use the retrieval skill.

### 1.4 Insertion Points

| point | after step | what memory adds |
|-------|-----------|-----------------|
| **IP-1** | Step 2 (Domain Classification) | Task memory: similar past tasks, quality deltas, winners |
| **IP-2** | Step 4 (Support Selection) | Effectiveness memory: per-role baselines for role selection confidence |
| **IP-3** | Step 5 (Confidence Evaluation) | Failure memory: known conflicts → lower confidence |

---

## 2. Current Orchestrator Decision Flow

### 2.1 Input/Output

```yaml
orchestrator_input:
  - router_output: lead/support candidates
  - role_registry: skills/meta/role-registry.md
  - patterns: memory/patterns/

orchestrator_output:
  - team_plan: lead + support + dependency order
  - task_cards: one per role
  - lifecycle_state: per-card status
  - human_review_gate: checklist
```

### 2.2 Decision Pipeline

```text
Phase 1: Understand the task
  (objective, domains, deliverables)
  ↓
Phase 2: Assess multi-agent need
  (domain >= 2 | required_roles >= 3 | task_dependency >= 2 | explicit)
  ↓
Phase 3: Build Team Plan
  Domain Detection → Capability Extraction → Pattern Matching → Role Selection → Dependency Ordering
  ↓
Phase 4: Assign task cards
  (one per role)
  ↓
Phase 5: Manage lifecycle
  (Created → Planned → Assigned → Executing → Reviewing → Integrated → Completed)
  ↓
Phase 6: Human review gate
  ↓
Phase 7: Hand off to collaboration runtime
```

### 2.3 Current Memory Consumption

| memory source | how used | integration point |
|---------------|----------|-------------------|
| `memory/patterns/` | Pattern matching by domain overlap | Phase 3 (Pattern Matching) |

**Gap**: Orchestrator reads `memory/patterns/` directly but does not use:
- Failure memory (past conflicts → role ordering adjustments)
- Anti-pattern memory (team inflation prevention)
- Effectiveness memory (per-role baselines)
- Hypothesis (should not be treated as patterns)

### 2.4 Insertion Points

| point | after step | what memory adds |
|-------|-----------|-----------------|
| **IP-4** | Phase 2 (Assess need) | Anti-pattern: team inflation check before activation |
| **IP-5** | Phase 3 (Pattern Matching) | Failure memory: role ordering adjustment for known conflicts |
| **IP-6** | Phase 3 (Role Selection) | Effectiveness memory: per-role quality baselines |
| **IP-7** | Phase 3 (Rule application R1-R10) | Failure + Anti-Pattern: additional constraints |

---

## 3. Current Memory Retrieval Capability

### 3.1 Available Assets

| asset | path | readiness |
|-------|------|-----------|
| Retrieval Protocol | `memory/retrieval-protocol.md` | ✅ ready |
| Retrieval Index | `memory/retrieval-index.yaml` | ✅ ready |
| Retrieval Skill | `memory/retrieval-skill.md` | ✅ ready |
| Test Dataset | `tests/memory/retrieval/` | ✅ 10 cases evaluated |
| Eval Report | `runtime/reports/phase-5.3-retrieval-evaluation.md` | ✅ precision=0.67 |

### 3.2 Retrieval Quality

```yaml
precision_at_5: 0.67
recall_at_5: 1.00
pollution_rate: 0.33
hypothesis_contamination: 0.00
```

---

## 4. Integration Architecture

### 4.1 Target Flow

```text
User Task
  ↓
Task Classification (Router Step 1-2)
  ↓
Memory Retrieval (query = classified task)
  ↓
  ├── Task Memory → Router Step 3 (Lead Selection)
  ├── Effectiveness → Router Step 4 (Support Selection)
  ├── Failure → Router Step 5 (Confidence) + Orchestrator Phase 3 (Role Ordering)
  ├── Pattern → Orchestrator Phase 3 (Pattern Matching)
  ├── Anti-Pattern → Orchestrator Phase 2 (Activation Check)
  └── Hypothesis → (flagged, not used for decisions)
  ↓
Router Decision (lead + support)
  ↓
Orchestrator Decision (team plan)
  ↓
Execution
```

### 4.2 Minimum Changes Required

| file | change | risk |
|------|--------|------|
| `skills/meta/agent-router/SKILL.md` | Add memory retrieval step after Domain Classification | Low — additive change |
| `skills/meta/agent-orchestrator/SKILL.md` | Add memory retrieval for anti-pattern/failure/effectiveness before Pattern Matching | Low — additive change |
| `memory/decision-support-protocol.md` | NEW — defines how memory influences decisions | None — new file |
| `runtime/logs/memory-decision-history.md` | NEW — decision provenance log | None — new file |

### 4.3 No-Change Zones

| file | reason |
|------|--------|
| `skills/meta/role-registry.md` | Not modified — roles are authoritative |
| `skills/meta/collaboration-runtime/SKILL.md` | Not modified — execution is separate concern |
| `memory/retrieval-index.yaml` | Not modified — read-only data |
| `memory/retrieval-skill.md` | Not modified — retrieval logic is stable |
| All `memory/tasks/`, `memory/patterns/`, etc. | Not modified — memory files are immutable |

---

## 5. Decision Priority Rules

```text
1. Current Task Requirements (hard — always authoritative)
2. Explicit Router Rules (hard — from skill-routing-matrix.md)
3. Safety / Hard Constraints (hard — role-registry.md, team size cap, conflict rules)
4. High-confidence relevant Memory (soft — evidence_level >= benchmark_evaluated)
5. Low-confidence Memory (soft — may be ignored)
6. Hypothesis Memory (never used for decisions — informational only)
```

---

## 6. Fallback Design

```yaml
fallback:
  memory_available:
    path: memory-augmented decision
  memory_unavailable:
    path: baseline decision (current Router/Orchestrator, no memory)
    log: "memory_unavailable_fallback"
  memory_retrieval_error:
    path: baseline decision
    log: "memory_retrieval_error"
  min_final_score_threshold:
    value: 0.15
    action: ignore memory below threshold
    log: "memory_below_threshold"
```

---

## 7. Risk Assessment

| risk | severity | mitigation |
|------|----------|------------|
| Memory overrides Router rule | HIGH | Priority rule: Router rules > Memory |
| Memory-induced regression | CRITICAL | Integration benchmark compares Mode A vs Mode B |
| Hypothesis treated as fact | HIGH | Hypothesis isolation + contamination check |
| Memory retrieval fails | MEDIUM | Fallback to baseline decision |
| Pollution causes wrong routing | HIGH | min_final_score threshold + forbidden_memory_violation check |
| Orchestrator anti-pattern not detected | MEDIUM | Add anti-pattern to Phase 2 activation check |
| Inconsistent pattern matching | LOW | Use retrieval-index.yaml as single source of truth |

---

## 8. Integration Benchmark Design

### 8.1 Test Cases

| id | task | category | expected memory types |
|----|------|----------|----------------------|
| I-01 | payment system | backend | task + failure + pattern |
| I-02 | RAG knowledge base | ai | task + success + effectiveness |
| I-03 | MySQL slow query | optimization | task + anti-pattern + effectiveness |
| I-04 | high concurrency | optimization | task + effectiveness |
| I-05 | frontend performance | frontend | task + effectiveness |
| I-06 | LLM tool calling | ai | task + success + effectiveness |
| I-07 | simple CRUD | backend | effectiveness (minimal) |
| I-08 | simple SQL issue | optimization | task + effectiveness |
| I-09 | cross-domain architecture | architecture | pattern + success + task |
| I-10 | conflicting memory | backend | task + failure (memory conflicts Router) |
| I-11 | hypothesis-only | cross-cutting | hypothesis (warning only) |
| I-12 | completely novel | iot | empty (no history) |

### 8.2 Mode A vs Mode B

```yaml
Mode A: Router/Orchestrator WITHOUT memory retrieval
Mode B: Router/Orchestrator WITH memory retrieval

comparison:
  - routing_accuracy
  - team_formation_accuracy
  - role_precision
  - team_inflation
  - decision_quality
```

---

## 9. Implementation Plan

### Step 2: Decision-Support Contract
Create `memory/decision-support-protocol.md` defining:
- decision_context schema
- memory_influence tracking
- decision_provenance format

### Step 3: Router Integration
Add memory retrieval step after Domain Classification:
- Query: classified task (category, domains, roles, keywords)
- Insert: memory context into lead selection and support selection
- Rule: Router rules always win over memory

### Step 4: Orchestrator Integration
Add memory retrieval before Pattern Matching:
- Anti-pattern check: team inflation prevention
- Failure check: role ordering adjustment
- Effectiveness check: per-role baselines
- Rule: Pattern matching still uses `memory/patterns/` directly

### Step 5-8: Benchmark + Evaluation
Run 12 integration tests, compare Mode A vs Mode B, log decisions.

---

*Integration Audit complete. Ready for Step 2: Decision-Support Contract.*