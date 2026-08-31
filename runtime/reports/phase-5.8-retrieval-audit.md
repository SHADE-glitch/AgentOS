# Phase 5.8 — Retrieval System Audit

**Date**: 2026-08-30
**Phase**: 5.8 — Adaptive Memory Retrieval & Routing Optimization
**Status**: Audit Complete

---

## 1. Current Retrieval Architecture

```text
Query Input (task description)
    │
    ▼
┌─────────────────────────────────────────────┐
│ retrieval-protocol.md (Phase 5.3)           │
│                                              │
│ 1. Normalize                                 │
│ 2. Classify (category, domains, difficulty)  │
│ 3. Candidate Selection (category filter)     │
│ 4. Metadata Filter (exclude deprecated)      │
│ 5. Relevance Scoring (static weights)        │
│ 6. Evidence Weighting (evidence_level)       │
│ 7. Hypothesis Flagging                       │
│ 8. Top-K Selection (k=5)                     │
│ 9. Deduplication                             │
│ 10. Context Formatting                       │
│                                              │
│ Data Source: retrieval-index.yaml (static)   │
└─────────────────────────────────────────────┘
    │
    ▼
Top-5 Memories → Router / Orchestrator
```

## 2. Current Scoring Formula

```text
final_score = relevance_score × evidence_weight

relevance_score = category_match  * 0.25
                + domain_match    * 0.20
                + type_boost      * 0.15
                + role_match      * 0.15
                + keyword_match   * 0.10
                + difficulty_match * 0.10
                + tag_overlap     * 0.05

evidence_weight: 0.6 (benchmark_evaluated), 0.3 (hypothesis), etc.
```

## 3. Current State Summary

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Retrieval Protocol | retrieval-protocol.md | active | Phase 5.3, deterministic pipeline |
| Retrieval Index | retrieval-index.yaml | active | 31 memories, all benchmark_evaluated |
| Memory Gates | memory-gates.md | defined | M1-M6, no runtime enforcement |
| Decision Support | decision-support-protocol.md | defined | Influence tracking, not feedback |
| Feedback Collector | collector/ | active | Phase 5.7.1, trace → candidate |
| Validator | promotion/validator.py | active | Phase 5.7.2, M1-M6 enforcement |
| Promoter | promotion/promoter.py | active | Phase 5.7.2, write-back |
| Evaluator | evaluation/evaluator.py | active | Phase 5.7.3, cross-group comparison |
| Effectiveness Results | evaluation/effectiveness-results.yaml | data | 1 pair evaluated, score 0.289 |

## 4. Problems Identified

### P1: Static Scoring — No Runtime Feedback

**Current**: Retrieval scores are computed from static metadata (category, tags, roles). Once set, they never change.

**Problem**: A memory that consistently helps (like P-001 in EXEC-1788092974, quality 3.05) receives the same score as one that doesn't help (EXEC-1788091972, quality 0.45).

**Impact**: The retrieval system cannot learn from execution outcomes.

### P2: No Performance Feedback Loop

**Current**: The Memory Feedback Pipeline (collector → validator → promoter → evaluator) produces data but does NOT feed back into retrieval.

**Problem**: effectiveness-results.yaml shows P-001/S-002 has latency -28% but quality -0.6. The retrieval system doesn't know this.

**Impact**: Retrieval cannot up-weight performance-improving memories or down-weight performance-harming memories.

### P3: No Usage Frequency Tracking

**Current**: retrieval-index.yaml has no `usage_count` or `last_used` fields.

**Problem**: Cannot distinguish frequently-used memories from rarely-used ones. Cannot implement decay.

### P4: No Memory Decay System

**Current**: memory-gates.md defines M6 (Staleness Gate) but it's only a conceptual gate. No actual decay implementation.

**Problem**: Stale or unused memories have the same retrieval weight as active ones.

### P5: No Success Rate Integration

**Current**: No concept of per-memory success rate. All traces are success, but quality varies.

**Problem**: Cannot weight memories by their historical contribution to quality.

### P6: Evidence Level Not Updated in Index

**Current**: Promoter updated P-001 and S-002 .md files to runtime_validated, but retrieval-index.yaml still shows benchmark_evaluated.

**Problem**: Retrieval system uses stale evidence levels.

### P7: No Routing Feedback

**Current**: decision-support-protocol.md defines `memory_influence` tracking but there's no mechanism to feed routing decisions back into retrieval.

**Problem**: Cannot learn which memories influence which routing decisions.

## 5. Missing Capabilities

```yaml
missing:
  - capability: "adaptive_scoring"
    description: "Retrieval scores that update based on runtime performance"
    current: "Static weights in retrieval-index.yaml"
    need: "Dynamic scoring with performance feedback"

  - capability: "memory_decay"
    description: "Automatic degradation of unused or low-performing memories"
    current: "M6 staleness gate (conceptual only)"
    need: "decay-policy.yaml + memory_decay.py"

  - capability: "usage_tracking"
    description: "Track how often each memory is retrieved and used"
    current: "No usage counters"
    need: "usage_count, last_retrieved, last_used in retrieval-index"

  - capability: "routing_feedback"
    description: "Close the loop: execution quality → retrieval weight adjustment"
    current: "No connection between evaluator and retrieval"
    need: "routing-feedback.yaml connecting task → memory → quality → weight_change"

  - capability: "performance_aware_ranking"
    description: "Memories that improve quality/tokens/latency rank higher"
    current: "Pure relevance-based ranking"
    need: "Composite score: relevance + performance_gain + confidence"

  - capability: "retrieval_index_sync"
    description: "Keep retrieval-index.yaml in sync with promoted memory files"
    current: "Index still shows benchmark_evaluated for P-001/S-002"
    need: "Auto-sync on promotion"
```

## 6. Data Flow: Current vs Target

```text
CURRENT:
  Task → retrieval-index.yaml → Relevance Score → Top-5 → Router
  Task → Execution → Trace → Collector → Validator → Promoter → Memory .md
  (no feedback loop)

TARGET:
  Task → retrieval-index.yaml → Adaptive Score → Top-5 → Router
                                  ↑                      │
                                  │                      ▼
                                  │               Execution → Trace
                                  │                      │
                                  └── Evaluator ←────────┘
                                  ↑
                                  │
                            Decay System
                                  │
                            Routing Feedback
```

## 7. What Needs to Be Built

| Step | What | Why |
|------|------|-----|
| 2 | retrieval-schema.yaml | Define adaptive scoring formula |
| 3 | retrieval_optimizer.py | Implement adaptive Top-K ranking |
| 4 | decay-policy.yaml + memory_decay.py | Degrade unused/low-performing memories |
| 5 | routing-feedback.yaml | Connect execution quality → retrieval |
| 6 | Integration test | 10 tasks, verify ranking |

## 8. Backward Compatibility Commitments

```yaml
do_not_modify:
  - "memory/*.md content"
  - "retrieval-protocol.md pipeline"
  - "decision-support-protocol.md"
  - "memory-gates.md"
  - "runtime execution code"
  - "telemetry schema"

do_modify:
  - "retrieval-index.yaml (add usage_count, last_used, performance_gain)"
  - "New files only in retrieval/ directory"
```