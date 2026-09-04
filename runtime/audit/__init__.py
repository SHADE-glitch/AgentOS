"""
Agent OS Audit Layer — Phase 8.9

Non-intrusive audit hooks for memory retrieval, evidence collection,
provenance generation, and TeamResult validation.

All modules are FAIL-SAFE: exceptions never block the main pipeline.

Modules:
  - retrieval_audit: Record every memory retrieval event
  - provenance_generator: Auto-generate file/symbol/git provenance
  - evidence_collector: Collect pre/post task evidence (git, test output)
  - team_result_validator: Validate TeamResult claims against evidence
  - audit_integration: Hooks to wire into loop_controller
"""