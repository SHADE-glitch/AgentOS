# Collector
# Phase 5.7.1 — Runtime Feedback Collector

## Purpose

The Collector bridges Phase 5.6 (Runtime) and Phase 5.7 (Memory Feedback).

```
runtime/traces/*.yaml  →  Collector  →  runtime/memory-feedback/memory-candidates.yaml
```

## Design

- **Input**: Runtime execution traces (`runtime/traces/EXEC-*.yaml`)
- **Output**: Memory candidates (`runtime/memory-feedback/memory-candidates.yaml`)
- **Constraint**: Does NOT modify Memory directly. Only produces candidates.

## Files

| File | Purpose |
|------|---------|
| `collector-schema.yaml` | Input/output contract, quality heuristics, generation rules |
| `collector-policy.md` | Operational rules, constraints, error handling |
| `README.md` | This file |

## Candidate Types

| Type | Meaning | Outcome |
|------|---------|---------|
| `reinforce` | Execution confirms existing memory | `promoted` |
| `weaken` | Execution contradicts or fails to support memory | `hold` |
| `create_hypothesis` | New insight not covered by existing memory | `hold` |

## Generation Rules

| Rule | Trigger | Type |
|------|---------|------|
| R1 | memory_used + success | reinforce |
| R2 | anti_pattern_alert + success | reinforce |
| R3 | memory_used + failure | weaken |
| R4 | memory_used + no_influence | weaken |
| R5 | success + high_quality + no_memory | create_hypothesis |
| R6 | risk_changed + success | reinforce |

## Safety

- Skips `memory_mode == 'off'` executions
- Requires `session_id`, `output_hash`, `tokens` for real evidence
- Never auto-promotes hypotheses
- Deduplicates by `(execution_id, target_memory)`
- Quality evaluated by heuristics, not AI

## Usage

The Collector is invoked by the Phase 5.7 Feedback Pipeline. It is not a standalone tool — it is a processing stage in the Memory Feedback Loop.