#!/usr/bin/env python3
"""
R7: Failed Test → Retry Execution

Tests that when a test failure is detected, the recovery executor
generates a RecoveryTask and the execution bridge correctly:
  1. Creates the RecoveryTask with proper context
  2. Delegates to the runtime executor (mock)
  3. Collects new evidence
  4. Verifies the result

This test uses a mock runtime executor to simulate OpenCode behavior.

How to run:
  cd /home/shade/.agents
  python3 benchmark/failure_recovery/r7_retry_execution.py
"""

import sys
import os
import json

BASE = "/home/shade/.agents"
sys.path.insert(0, os.path.join(BASE, "runtime", "recovery"))

from recovery_executor import (
    create_recovery_task,
    execute_recovery,
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


# ── Mock Runtime Executor ────────────────────────────────────────
# Simulates OpenCode behavior for testing

def mock_runtime_success(task_id, task_text, decision_context, model, provider, project_root):
    """Simulate a successful recovery execution."""
    return {
        "status": "success",
        "output": "Fixed the test and it now passes",
        "test_command": "pytest test_module.py",
        "test_exit_code": 0,
        "test_stdout": "10 passed in 0.5s",
        "test_stderr": "",
        "execution_id": f"EXEC-{task_id}",
        "latency_ms": 500,
    }


def mock_runtime_failure(task_id, task_text, decision_context, model, provider, project_root):
    """Simulate a failed recovery execution."""
    return {
        "status": "error",
        "output": "Unable to fix the test",
        "test_command": "pytest test_module.py",
        "test_exit_code": 1,
        "test_stdout": "8 passed, 2 failed",
        "test_stderr": "FAILED test_broken - AssertionError",
        "execution_id": f"EXEC-{task_id}",
        "latency_ms": 500,
    }


def mock_runtime_no_evidence(task_id, task_text, decision_context, model, provider, project_root):
    """Simulate execution that produces no test evidence."""
    return {
        "status": "error",
        "output": "Something went wrong",
        "test_command": "",
        "test_exit_code": None,
        "test_stdout": "",
        "test_stderr": "",
        "execution_id": f"EXEC-{task_id}",
        "latency_ms": 500,
    }


# ── Test 1: Successful recovery execution ──
print("=" * 60)
print("R7: Retry Execution")
print("=" * 60)

print("\n1. Successful recovery execution (test passes after retry)")
recovery_decision = {
    "task_id": "R7-001",
    "loop_id": "LOOP-R7-001",
    "failure_events": [
        {"type": "failed_tests", "severity": "high", "reason": "Test exit_code=1",
         "description": "Tests failed with exit code 1"}
    ],
    "recovery_actions": [
        {"action": "inspect_and_retry", "description": "Inspect test failure and retry",
         "evidence_required": ["test_command", "test_exit_code", "test_stdout"]}
    ],
    "retry_count": 0,
    "recovery_plan": {"target_stages": ["runtime"]},
    "exec_result": {"status": "error", "test_exit_code": 1},
}

original_task = {
    "task_text": "Fix the failing test",
    "decision_context": {},
    "model": "",
    "provider": "opencode",
    "project_root": BASE,
}

task = create_recovery_task(recovery_decision, original_task, "R7-SESSION")

result = execute_recovery(task, mock_runtime_success, "R7-SESSION")

assert_true(result["success"], "recovery succeeded")
assert_true(result["evidence_collected"], "evidence was collected")
assert_true(result["verified"], "result was verified")
assert_equal(result["new_result"]["test_exit_code"], 0, "test_exit_code = 0 after recovery")
assert_true(len(result["errors"]) == 0, "no errors")

# ── Test 2: Failed recovery execution (test still fails) ──
print("\n2. Failed recovery execution (test still fails after retry)")
task2 = create_recovery_task(recovery_decision, original_task, "R7-SESSION")
result2 = execute_recovery(task2, mock_runtime_failure, "R7-SESSION")

assert_true(not result2["success"], "recovery did NOT succeed (expected)")
assert_equal(result2["new_result"]["test_exit_code"], 1, "test_exit_code still = 1")
assert_true(len(result2["errors"]) > 0, "errors recorded")

# ── Test 3: Recovery with no evidence produced ──
print("\n3. Recovery execution with no evidence produced")
task3 = create_recovery_task(recovery_decision, original_task, "R7-SESSION")
result3 = execute_recovery(task3, mock_runtime_no_evidence, "R7-SESSION")

assert_true(result3["new_result"]["test_exit_code"] is None, "test_exit_code is None")
assert_true(not result3["evidence_collected"], "evidence NOT collected (expected)")
assert_true(not result3["verified"], "not verified (expected)")

# ── Test 4: RecoveryTask structure in recovery result ──
print("\n4. RecoveryTask preserved in result")
recovery_task = result.get("recovery_task", {})
assert_equal(recovery_task.get("task_id"), "R7-001", "task_id in result")
assert_equal(recovery_task.get("retry_attempt"), 1, "retry_attempt in result")
assert_true("failure_reason" in recovery_task, "failure_reason in result")

# ── Test 5: Session artifact saved ──
print("\n5. Recovery task result artifact saved")
artifact_path = os.path.join(BASE, "reports", "R7-SESSION", "recovery-task-R7-001.json")
assert_true(os.path.exists(artifact_path), f"artifact saved: {artifact_path}")

if os.path.exists(artifact_path):
    with open(artifact_path) as f:
        artifact = json.load(f)
    assert_true("recovery_task" in artifact, "artifact has recovery_task")
    assert_true("result" in artifact, "artifact has result")
    assert_true("errors" in artifact["result"], "artifact has errors field")
    # Last execution was no_evidence → success=False
    assert_true(not artifact["result"]["success"], "artifact records failure (last execution)")

# ── Summary ──
print(f"\n{'=' * 60}")
print(f"R7 Results: {PASS} PASS, {FAIL} FAIL")
print(f"{'PASSED' if FAIL == 0 else 'FAILED'}")
print(f"{'=' * 60}")
sys.exit(0 if FAIL == 0 else 1)