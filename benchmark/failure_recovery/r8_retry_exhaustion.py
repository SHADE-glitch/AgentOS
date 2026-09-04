#!/usr/bin/env python3
"""
R8: Retry Exhaustion

Tests that the recovery loop correctly enforces the retry budget:
  - MAX_RECOVERY_RETRIES = 2 hard limit
  - After 2 retries, check_recovery_budget() reports exhausted
  - should_retry() returns False when budget exhausted
  - No infinite loops

How to run:
  cd /home/shade/.agents
  python3 benchmark/failure_recovery/r8_retry_exhaustion.py
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
from retry_controller import should_retry, record_retry_attempt, get_retry_count
from recovery_planner import plan_recovery

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


# ── Test 1: Fresh budget ──
print("=" * 60)
print("R8: Retry Exhaustion")
print("=" * 60)

print("\n1. Fresh budget — no retries recorded")
budget = check_recovery_budget("R8-001", "R8-SESSION")
assert_equal(budget["remaining"], MAX_RECOVERY_RETRIES, "remaining = MAX_RECOVERY_RETRIES")
assert_equal(budget["used"], 0, "used = 0")
assert_true(not budget["exhausted"], "not exhausted")

# ── Test 2: After 1 retry ──
print("\n2. After 1 retry recorded")
failure_events = [
    {"type": "failed_tests", "severity": "high", "reason": "Test exit_code=1",
     "description": "Tests failed"}
]
recovery_plan = plan_recovery(failure_events, "R8-001", "LOOP-R8", retry_count=0)

can_retry, reason = should_retry(recovery_plan, 0)
assert_true(can_retry, "should_retry(0) = True")
print(f"    reason: {reason}")

record_retry_attempt("R8-001", "LOOP-R8", 1, recovery_plan, failure_events,
                     result={"status": "failed"}, session_id="R8-SESSION")

budget2 = check_recovery_budget("R8-001", "R8-SESSION")
assert_equal(budget2["remaining"], MAX_RECOVERY_RETRIES - 1, "remaining decreased by 1")
assert_equal(budget2["used"], 1, "used = 1")
assert_true(not budget2["exhausted"], "not exhausted yet")

# ── Test 3: After 2 retries (exhausted) ──
print("\n3. After 2 retries — budget exhausted")
record_retry_attempt("R8-001", "LOOP-R8", 2, recovery_plan, failure_events,
                     result={"status": "failed"}, session_id="R8-SESSION")

budget3 = check_recovery_budget("R8-001", "R8-SESSION")
assert_equal(budget3["remaining"], 0, "remaining = 0")
assert_equal(budget3["used"], MAX_RECOVERY_RETRIES, "used = MAX_RECOVERY_RETRIES")
assert_true(budget3["exhausted"], "exhausted = True")

# ── Test 4: should_retry returns False when exhausted ──
print("\n4. should_retry returns False when exhausted")
recovery_plan_exhausted = plan_recovery(failure_events, "R8-001", "LOOP-R8", retry_count=2)
can_retry2, reason2 = should_retry(recovery_plan_exhausted, 2)
assert_true(not can_retry2, "should_retry(2) = False")
print(f"    reason: {reason2}")

# ── Test 5: get_retry_count confirms exhaustion ──
print("\n5. get_retry_count confirms count")
count = get_retry_count("R8-001", session_id="R8-SESSION")
assert_equal(count, MAX_RECOVERY_RETRIES, "retry count = MAX_RECOVERY_RETRIES")

# ── Test 6: RecoveryTask with exhausted budget ──
print("\n6. RecoveryTask with retry_count=MAX_RECOVERY_RETRIES")
recovery_decision = {
    "task_id": "R8-001",
    "loop_id": "LOOP-R8",
    "failure_events": failure_events,
    "recovery_actions": [
        {"action": "inspect_and_retry", "description": "Retry tests",
         "evidence_required": ["test_command", "test_exit_code"]}
    ],
    "retry_count": MAX_RECOVERY_RETRIES,
    "recovery_plan": {"target_stages": ["runtime"]},
    "exec_result": {"status": "error"},
}
original_task = {
    "task_text": "Fix the test",
    "decision_context": {},
    "model": "",
    "provider": "opencode",
    "project_root": BASE,
}
task = create_recovery_task(recovery_decision, original_task, "R8-SESSION")
assert_equal(task["retry_attempt"], MAX_RECOVERY_RETRIES + 1, "retry_attempt = MAX_RETRIES + 1")
assert_equal(task["retry_context"]["attempt"], MAX_RECOVERY_RETRIES + 1, "context.attempt = MAX_RETRIES + 1")

# ── Test 7: No infinite loop — check MAX_RECOVERY_RETRIES is finite ──
print("\n7. Safety: MAX_RECOVERY_RETRIES is finite and small")
assert_true(MAX_RECOVERY_RETRIES == 2, "MAX_RECOVERY_RETRIES = 2 (hard limit)")
assert_true(MAX_RECOVERY_RETRIES < 10, "MAX_RECOVERY_RETRIES < 10 (no unbounded growth)")

# ── Summary ──
print(f"\n{'=' * 60}")
print(f"R8 Results: {PASS} PASS, {FAIL} FAIL")
print(f"{'PASSED' if FAIL == 0 else 'FAILED'}")
print(f"{'=' * 60}")
sys.exit(0 if FAIL == 0 else 1)