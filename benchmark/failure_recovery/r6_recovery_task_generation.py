#!/usr/bin/env python3
"""
R6: Runtime Failure → Recovery Task Generation

Tests that when a runtime failure is detected, the recovery executor
correctly generates a RecoveryTask with all required fields.

What is tested:
  - RecoveryDecision parsing
  - RecoveryTask structure (task_id, original_task, failure_reason,
    required_action, retry_context, evidence_required)
  - Retry attempt counter
  - Session ID propagation
  - Budget check

How to run:
  cd /home/shade/.agents
  python3 benchmark/failure_recovery/r6_recovery_task_generation.py
"""

import sys
import os
import json

BASE = "/home/shade/.agents"
sys.path.insert(0, os.path.join(BASE, "runtime", "recovery"))

from recovery_executor import (
    create_recovery_task,
    check_recovery_budget,
    MAX_RECOVERY_RETRIES,
)

PASS = 0
FAIL = 0


def assert_true(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {msg}")
    else:
        FAIL += 1
        print(f"  FAIL: {msg}")


def assert_equal(a, b, msg):
    global PASS, FAIL
    if a == b:
        PASS += 1
        print(f"  PASS: {msg} ({a})")
    else:
        FAIL += 1
        print(f"  FAIL: {msg} (expected {b}, got {a})")


# ── Test 1: Basic RecoveryTask generation ──
print("=" * 60)
print("R6: Recovery Task Generation")
print("=" * 60)

print("\n1. Create RecoveryTask from failed_tests event")
recovery_decision = {
    "task_id": "R6-001",
    "loop_id": "LOOP-R6-001",
    "failure_events": [
        {"type": "failed_tests", "severity": "high",
         "reason": "Test exit_code=1", "description": "Tests failed with exit code 1"}
    ],
    "recovery_actions": [
        {"action": "inspect_and_retry",
         "description": "Inspect test failure output and retry",
         "evidence_required": ["test_command", "test_exit_code", "test_stdout"]}
    ],
    "retry_count": 0,
    "recovery_plan": {"target_stages": ["runtime"]},
    "exec_result": {"status": "error", "test_exit_code": 1},
}

original_task = {
    "task_text": "Fix the failing test in test_module.py",
    "decision_context": {"task_classification": "bug_fix"},
    "model": "test-model",
    "provider": "opencode",
    "project_root": BASE,
}

task = create_recovery_task(recovery_decision, original_task, "R6-SESSION")

assert_equal(task["task_id"], "R6-001", "task_id")
assert_true(task["original_task"] == "Fix the failing test in test_module.py", "original_task preserved")
assert_true("failed_tests" in task["failure_reason"], "failure_reason contains failure type")
assert_true("test" in task["failure_reason"].lower(), "failure_reason contains failure type in lowercase")
assert_true(len(task["required_action"]) > 0, "required_action is non-empty")
assert_equal(task["retry_attempt"], 1, "retry_attempt = 1 (first retry)")
assert_equal(task["session_id"], "R6-SESSION", "session_id propagated")
assert_true("test_command" in task["evidence_required"], "evidence_required has test_command")
assert_true("test_exit_code" in task["evidence_required"], "evidence_required has test_exit_code")
assert_true("test_stdout" in task["evidence_required"], "evidence_required has test_stdout")
assert_equal(task["retry_context"]["attempt"], 1, "retry_context.attempt = 1")
assert_equal(task["retry_context"]["max_retries"], MAX_RECOVERY_RETRIES, "retry_context.max_retries")
assert_true("hint" in task["retry_context"], "retry_context has hint")

# ── Test 2: RecoveryTask with multiple failures ──
print("\n2. Create RecoveryTask from multiple failure events")
recovery_decision["failure_events"] = [
    {"type": "failed_tests", "severity": "high", "reason": "Test exit_code=1", "description": "Tests failed"},
    {"type": "incomplete_teamresult", "severity": "medium", "reason": "Missing summary", "description": "TeamResult incomplete"},
]
recovery_decision["recovery_actions"] = [
    {"action": "inspect_and_retry", "description": "Inspect test failure and retry",
     "evidence_required": ["test_command", "test_exit_code"]},
    {"action": "regenerate_team_result", "description": "Regenerate TeamResult",
     "evidence_required": ["team_result"]},
]

task2 = create_recovery_task(recovery_decision, original_task, "R6-SESSION")

assert_true("failed_tests" in task2["failure_reason"], "multi-failure: contains failed_tests")
assert_true("incomplete_teamresult" in task2["failure_reason"], "multi-failure: contains incomplete_teamresult")
assert_true("test_command" in task2["evidence_required"], "multi-failure: evidence has test_command")
assert_true("team_result" in task2["evidence_required"], "multi-failure: evidence has team_result")
assert_true("failed_tests" in task2["retry_context"]["failure_types"], "multi-failure: context has failed_tests")

# ── Test 3: RecoveryTask with retry_count > 0 ──
print("\n3. Create RecoveryTask with retry_count=1 (second attempt)")
recovery_decision["retry_count"] = 1
recovery_decision["failure_events"] = [
    {"type": "runtime_error", "severity": "high", "reason": "Provider error", "description": "Runtime failed"}
]
recovery_decision["recovery_actions"] = [
    {"action": "retry_execution", "description": "Retry runtime execution",
     "evidence_required": ["test_command", "test_exit_code"]},
]

task3 = create_recovery_task(recovery_decision, original_task, "R6-SESSION")
assert_equal(task3["retry_attempt"], 2, "retry_attempt = 2 (second retry)")
assert_equal(task3["retry_context"]["attempt"], 2, "retry_context.attempt = 2")

# ── Test 4: Budget check ──
print("\n4. Check recovery budget")
budget = check_recovery_budget("R6-001", "R6-SESSION")
assert_true(budget["max"] == MAX_RECOVERY_RETRIES, "budget.max = MAX_RECOVERY_RETRIES")
assert_true(budget["remaining"] >= 0, "budget.remaining >= 0")
assert_true(not budget["exhausted"], "budget not exhausted (no retries recorded)")

# ── Test 5: Empty failure events ──
print("\n5. Create RecoveryTask with no failure events (edge case)")
recovery_decision["failure_events"] = []
recovery_decision["recovery_actions"] = []
task5 = create_recovery_task(recovery_decision, original_task, "R6-SESSION")
assert_true(task5["failure_reason"] == "", "empty failures → empty failure_reason")
assert_true(task5["evidence_required"] == [], "empty failures → empty evidence_required")

# ── Summary ──
print(f"\n{'=' * 60}")
print(f"R6 Results: {PASS} PASS, {FAIL} FAIL")
print(f"{'PASSED' if FAIL == 0 else 'FAILED'}")
print(f"{'=' * 60}")
sys.exit(0 if FAIL == 0 else 1)