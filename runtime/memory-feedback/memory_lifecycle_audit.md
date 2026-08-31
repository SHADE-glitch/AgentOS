# Memory Lifecycle Audit
# Phase 5.7.2 — Pre-execution baseline

audit_date: "2026-08-30"
audit_scope:
  - "/home/shade/.agents/memory/"
  - "/home/shade/.agents/runtime/memory-feedback/"

# =============================================================================
# 1. Memory Inventory (31 entries)
# =============================================================================

inventory:
  total_memories: 31
  by_type:
    task: 10
    failure: 2
    success: 2
    pattern: 2
    anti_pattern: 1
    hypothesis: 2
    effectiveness: 12

  by_status:
    observed: 31       # ALL stuck here
    new: 0
    validated: 0       # NO memory has been validated
    trusted: 0
    deprecated: 0

  by_evidence_level:
    benchmark_evaluated: 31   # ALL at lowest runtime-free level
    runtime_validated: 0      # NO memory has runtime evidence
    independent_validated: 0
    real_project_validated: 0
    production_validated: 0

  by_confidence:
    low: 31            # ALL at lowest confidence
    medium: 0
    high: 0

# =============================================================================
# 2. Lifecycle State Machine
# =============================================================================

lifecycle:
  defined_states: ["new", "observed", "validated", "trusted", "deprecated"]

  current_state: "ALL memories at 'observed' — no promotion has ever occurred"

  state_transitions:
    new_to_observed:
      defined: true
      implemented: false
      notes: "No mechanism to create new memory entries"

    observed_to_validated:
      defined: true   # Memory Gates M1-M6
      implemented: false
      notes: "Gates defined but no validator exists to apply them"

    validated_to_trusted:
      defined: true   # promotion-policy.yaml
      implemented: false
      notes: "Policy defined but no promoter exists to execute it"

    validated_to_rejected:
      defined: true   # rejection-policy.yaml
      implemented: false
      notes: "Policy defined but no rejection mechanism exists"

    any_to_deprecated:
      defined: true
      implemented: false
      notes: "No deprecation mechanism"

# =============================================================================
# 3. Candidate Inventory (14 entries)
# =============================================================================

candidates:
  file: "runtime/memory-feedback/memory-candidates.yaml"
  total: 14
  by_type:
    reinforce: 14
    weaken: 0
    create_hypothesis: 0
  by_outcome:
    promoted: 14      # ALL marked as "promoted" but no actual promotion executed
    hold: 0
    rejected: 0

  affected_memories:
    - AP-001: 1 candidate
    - T-010: 1 candidate
    - F-002: 2 candidates
    - T-004: 2 candidates
    - P-002: 2 candidates
    - E-007: 2 candidates
    - T-005: 1 candidate
    - S-001: 1 candidate
    - E-004: 1 candidate
    - E-005: 1 candidate

  gap: |
    14 candidates exist with outcome: promoted.
    But NO memory has been updated.
    Candidates are decoupled from actual memory files.
    The bridge from candidate → memory update is missing.

# =============================================================================
# 4. Existing Infrastructure
# =============================================================================

existing:
  feedback_schema:
    file: "runtime/memory-feedback/feedback-schema.yaml"
    status: "Defined 5-stage pipeline, not executed"

  promotion_policy:
    file: "runtime/memory-feedback/promotion-policy.yaml"
    status: "Defined rules, no executor"

  rejection_policy:
    file: "runtime/memory-feedback/rejection-policy.yaml"
    status: "Defined rules, no executor"

  collector:
    file: "runtime/memory-feedback/collector/collector.py"
    status: "Working, generates candidates from traces"

  memory_gates:
    file: "memory/memory-gates.md"
    status: "Defined M1-M6, no validator"

  retrieval_index:
    file: "memory/retrieval-index.yaml"
    status: "31 entries indexed, all at benchmark_evaluated"

# =============================================================================
# 5. Gap Analysis
# =============================================================================

gaps:
  - gap: "candidate_validation"
    description: "No validator to check if candidates meet promotion criteria"
    severity: "critical"
    needed: "validator.py"

  - gap: "promotion_engine"
    description: "No engine to apply validated candidates to memory files"
    severity: "critical"
    needed: "promoter.py"

  - gap: "memory_write_back"
    description: "No mechanism to update memory/*.md files with new evidence"
    severity: "critical"
    needed: "promoter.py write-back logic"

  - gap: "rejection_execution"
    description: "No mechanism to reject candidates and record reasons"
    severity: "high"
    needed: "validator.py rejection path"

  - gap: "deduplication"
    description: "No deduplication of (execution_id, memory_id) pairs"
    severity: "medium"
    notes: "Collector has dedup but validator doesn't cross-check"

# =============================================================================
# 6. Verdict
# =============================================================================

verdict:
  lifecycle_defined: true
  lifecycle_implemented: false
  states_exist_in_files: true
  states_enforced_by_code: false
  candidates_exist: true
  candidates_validated: false
  memories_promoted: false
  promotion_engine_exists: false

  summary: |
    The Memory lifecycle is defined (new → observed → validated → trusted → deprecated).
    All 31 memories are at 'observed' with 'benchmark_evaluated' evidence.
    14 candidates exist with 'promoted' outcome but no actual promotion has occurred.
    Missing: validator (to check candidates) and promoter (to apply to memory files).
    Phase 5.7.2 must build these two components.