# Collector Policy
# Phase 5.7.1 — Runtime Feedback Collector
# Operational rules and constraints for the Collector

version: "1.0"
phase: "5.7.1"
status: "active"

# =============================================================================
# 1. Operational Rules
# =============================================================================

## 1.1 Collector is Read-Only on Memory

The Collector **reads** Runtime traces and **writes** candidates.
It **never** modifies:
- memory/retrieval-index.yaml
- memory/*/*.md
- memory/*/*.yaml
- Any existing Memory entry

The Feedback Pipeline (Phase 5.7) is responsible for promotion/rejection.

## 1.2 Input Validation

Before processing any trace, the Collector must verify:

```yaml
validation:
  - check: "execution_id exists and is unique"
    fail: "Skip trace"
  - check: "session_id is present"
    fail: "Skip trace. Cannot verify as real execution."
  - check: "output_hash is present"
    fail: "Skip trace. Cannot verify output integrity."
  - check: "tokens.total > 0"
    fail: "Skip trace. Suspicious zero-token execution."
  - check: "memory_mode == 'on'"
    fail: "Skip trace. Memory OFF is baseline, not for feedback."
```

## 1.3 Candidate Deduplication

Before creating a candidate, check:
1. Does a candidate already exist for this `(execution_id, target_memory)` pair?
2. If yes → skip. Do not create duplicate.
3. If no → create candidate.

## 1.4 Quality Score Assignment

Quality scores are assigned heuristically based on the response structure.
The Collector does NOT use AI to evaluate quality — it uses structural rules.

See `collector-schema.yaml` for the heuristic rules.

## 1.5 Candidate ID Format

```
CAND-{sequence_number}
```

Sequence starts from the highest existing candidate ID + 1.

# =============================================================================
# 2. Processing Flow
# =============================================================================

```text
For each trace in runtime/traces/EXEC-*.yaml:
  1. Validate input (session_id, output_hash, tokens, memory_mode)
  2. Skip if memory_mode == 'off'
  3. Skip if already processed (deduplication)
  4. Evaluate quality (heuristic scoring)
  5. Apply generation rules (R1-R6)
  6. For each triggered rule:
     a. Create candidate
     b. Assign candidate_type
     c. Assign outcome
     d. Write reasoning
  7. Append to memory-candidates.yaml
```

# =============================================================================
# 3. Candidate Generation Rules (summary)
# =============================================================================

| Rule | Condition | Candidate Type | Outcome |
|------|-----------|---------------|---------|
| R1 | memory_used + success | reinforce | promoted |
| R2 | anti_pattern_alert + success | reinforce | promoted |
| R3 | memory_used + failure | weaken | hold |
| R4 | memory_used + no_influence | weaken | hold |
| R5 | success + high_quality + no_memory | create_hypothesis | hold |
| R6 | risk_changed + success | reinforce | promoted |

# =============================================================================
# 4. Constraints
# =============================================================================

constraints:
  - "Do not modify Memory directly"
  - "Do not fabricate execution data"
  - "Do not create non-existent Memory references"
  - "Do not auto-promote hypotheses"
  - "Do not process Memory OFF executions"
  - "Do not create duplicate candidates"
  - "Do not evaluate quality with AI — use heuristics only"
  - "Do not exceed 5 candidates per execution"

# =============================================================================
# 5. Error Handling
# =============================================================================

error_handling:
  trace_not_found:
    action: "Skip. Log warning."
  trace_missing_fields:
    action: "Skip. Log which fields are missing."
  trace_parse_error:
    action: "Skip. Log error with trace path."
  memory_not_found:
    action: "Skip candidate for that memory. Log warning."
  duplicate_candidate:
    action: "Skip. Do not create duplicate."
  output_file_write_error:
    action: "Fail. Do not produce partial output."