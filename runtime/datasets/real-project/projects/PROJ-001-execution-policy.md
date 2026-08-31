# Execution Policy — PROJ-001 (aiview)
# Phase 5.9.1 — Real Project Onboarding
# Generated: 2026-08-31

project_id: PROJ-001
project_name: "aiview — AI 面试陪练与智能反馈平台"

# ── Execution Pipeline ──

pipeline:
  steps:
    - task_received
    - routing_completed
    - memory_retrieved
    - memory_applied
    - orchestration_completed
    - agent_started
    - agent_completed
    - execution_completed

# ── Runtime Settings ──

runtime:
  controller: runtime/loop-controller/loop_controller.py
  default_model: opencode/big-pickle
  fallback_models:
    - opencode/big-pickle
    - opencode/nemotron-3.5-lightning-free
  timeout_ms: 120000
  max_retries: 1

# ── Human Review ──

human_review:
  enabled: true
  required: true
  minimum_reviewers: 1
  reviewer_role: developer
  review_triggers:
    - every_execution
  review_items:
    - agent_output_correctness
    - memory_was_helpful
    - memory_caused_regression
    - decision_quality
    - code_quality

# ── Evidence Rules ──

evidence:
  first_observation: candidate
  second_observation: candidate
  third_step: validation
  after_validation: human_review
  final: promotion
  note: |
    第一次观察产生 candidate，第二次独立观察产生第二个 candidate，
    第三步进行 validation，然后 human review，最后 promotion。
    禁止第一次成功就设为 trusted memory。

# ── Constraints ──

constraints:
  - do_not_modify_project_source_code
  - do_not_commit_code
  - do_not_run_tests_against_production
  - do_not_promote_automatically
  - do_not_create_agents_for_project
  - use_existing_skills_only