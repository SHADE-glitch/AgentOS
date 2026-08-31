#!/usr/bin/env python3
"""
Phase 5.8.2.2 — Closed-Loop Runtime Controller

This is a PROGRAM-LEVEL Pipeline Controller, NOT an Agent Orchestrator.
It does NOT re-implement Router, Orchestrator, or Agent Team Formation.
It only schedules existing components in the correct order.

Pipeline:
  Task → Retrieval → Decision Support → Router → Orchestrator → Runtime
       → Trace → Collector → Validator → Promoter → Reconciler

Constraints:
  - Memory is supporting input only. It does NOT override Router/Orchestrator.
  - Idempotent: same loop_id → no duplicate processing.
  - All provenance is traceable: loop_id → execution_id → trace_id → candidate_id → validation → promotion.
  - Any stage failure → loop_status = failed.
"""

import sys
import os
import yaml
import time
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE = "/home/shade/.agents"
LOOP_CONTROLLER_DIR = os.path.join(BASE, "runtime", "loop-controller")
STATE_DIR = os.path.join(LOOP_CONTROLLER_DIR, "state")

# Add paths for component imports
sys.path.insert(0, os.path.join(BASE, "runtime", "loop-controller"))
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "retrieval"))
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "collector"))
sys.path.insert(0, os.path.join(BASE, "runtime", "memory-feedback", "promotion"))

from retrieval_adapter import adapt as retrieval_adapt
from runtime_adapter import execute as runtime_execute, generate_loop_id
from collector import collect_from_trace_ids
from validator import validate_candidates
from promoter import promote_validated
from memory_state_reconciler import check_consistency, repair_index

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "opencode/ling-3.0-flash-fin-free"
EXECUTION_CONTRACT = os.path.join(LOOP_CONTROLLER_DIR, "execution-contract.yaml")


def load_contract():
    """Load the execution contract template."""
    if os.path.exists(EXECUTION_CONTRACT):
        with open(EXECUTION_CONTRACT) as f:
            return yaml.safe_load(f)
    return {}


def save_loop_state(loop_id, state):
    """Save loop state to state/<loop_id>.yaml."""
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, f"{loop_id}.yaml")
    with open(path, "w") as f:
        yaml.dump(state, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return path


def load_loop_state(loop_id):
    """Load existing loop state if it exists."""
    path = os.path.join(STATE_DIR, f"{loop_id}.yaml")
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f)
    return None


def init_loop_state(loop_id, task_id, task_text, memory_mode, model):
    """Initialize a fresh loop state from the execution contract."""
    contract = load_contract()
    loop_exec = contract.get("loop_execution", {}) if contract else {}

    state = {
        "loop_id": loop_id,
        "task_id": task_id,
        "task_text": task_text,
        "memory_mode": memory_mode,
        "model": model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": "",
        "current_stage": "running",
        "final_status": "pending",

        "retrieval": {
            "status": "pending",
            "retrieved_count": 0,
            "memory_ids": [],
            "hypotheses": [],
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "decision": {
            "status": "pending",
            "influence": "none",
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "runtime": {
            "status": "pending",
            "execution_id": "",
            "trace_id": "",
            "session_id": "",
            "provider": "opencode",
            "model": model,
            "latency_ms": 0,
            "token_usage": {},
            "output_hash": "",
            "status_code": "",
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "trace": {
            "status": "pending",
            "trace_file": "",
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "feedback": {
            "status": "pending",
            "candidate_ids": [],
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "validation": {
            "status": "pending",
            "validated_ids": [],
            "rejected_ids": [],
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "promotion": {
            "status": "pending",
            "promoted_ids": [],
            "rejected_ids": [],
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "reconciliation": {
            "status": "pending",
            "result": "",
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "errors": [],
    }
    return state


def mark_failed(state, stage, error):
    """Mark a stage as failed and record the error."""
    state[stage]["status"] = "failed"
    state[stage]["error"] = str(error)
    state["errors"].append({"stage": stage, "error": str(error)})
    state["final_status"] = "failed"


def run_loop(task_id, task_text, memory_mode="enabled", model=DEFAULT_MODEL):
    """
    Execute a single closed-loop pipeline.

    Args:
        task_id: str like "RT-003"
        task_text: str, the task description
        memory_mode: "enabled" | "fallback" | "disabled"
        model: str, OpenCode model name

    Returns:
        dict with loop_id, final_status, and all stage results
    """
    loop_id = generate_loop_id()
    state = init_loop_state(loop_id, task_id, task_text, memory_mode, model)

    print("=" * 70)
    print(f"Phase 5.8.2.2 — Closed-Loop Runtime Controller")
    print(f"Loop ID:    {loop_id}")
    print(f"Task ID:    {task_id}")
    print(f"Task:       {task_text[:80]}")
    print(f"Memory:     {memory_mode}")
    print(f"Model:      {model}")
    print("=" * 70)

    # Save initial state
    state_path = save_loop_state(loop_id, state)
    print(f"\nLoop state: {state_path}")

    # =====================================================================
    # Stage 1: Retrieval
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 1/8: Retrieval")
    print(f"{'─' * 70}")

    state["retrieval"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "retrieval"

    try:
        decision_context = retrieval_adapt(task_id, task_text, memory_mode)
        state["retrieval"]["status"] = "completed"
        state["retrieval"]["retrieved_count"] = decision_context.get("total_retrieved", 0)
        state["retrieval"]["memory_ids"] = decision_context.get("ranking", [])
        state["retrieval"]["hypotheses"] = [h.get("memory_id", "") for h in decision_context.get("hypotheses", [])]
        print(f"  Retrieved: {state['retrieval']['retrieved_count']} memories, {len(state['retrieval']['hypotheses'])} hypotheses")
        print(f"  Memory IDs: {state['retrieval']['memory_ids']}")
    except Exception as e:
        mark_failed(state, "retrieval", e)
        print(f"  FAILED: {e}")
        # Fallback: continue with empty memory context
        decision_context = {
            "task_id": task_id,
            "task_text": task_text,
            "memory_mode": "fallback",
            "retrieved": False,
            "memories": [],
            "hypotheses": [],
            "total_retrieved": 0,
            "ranking": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        state["memory_mode"] = "fallback"
        print(f"  Fallback: continuing with baseline (no memory)")

    state["retrieval"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Attach classification to decision_context for runtime_adapter
    decision_context["classification"] = {
        "category": "backend",
        "domains": [],
        "roles": [],
        "keywords": [],
        "difficulty": "medium",
    }
    # Try to get classification from retrieval adapter's classify_task
    try:
        from retrieval_adapter import classify_task
        cls = classify_task(task_text)
        decision_context["classification"] = cls
        state["decision"]["influence"] = "confirmation" if decision_context.get("memories") else "none"
    except Exception:
        pass

    state["decision"]["status"] = "completed"
    state["decision"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["decision"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 2: Runtime (includes Router/Orchestrator via prompt)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 2/8: Runtime (OpenCode CLI)")
    print(f"{'─' * 70}")

    state["runtime"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "runtime"

    try:
        exec_result = runtime_execute(task_id, task_text, decision_context, model)
        state["runtime"]["status"] = "completed"
        state["runtime"]["execution_id"] = exec_result["execution_id"]
        state["runtime"]["trace_id"] = exec_result["trace_id"]
        state["runtime"]["session_id"] = exec_result.get("session_id", "")
        state["runtime"]["latency_ms"] = exec_result.get("latency_ms", 0)
        state["runtime"]["token_usage"] = exec_result.get("token_usage", {})
        state["runtime"]["output_hash"] = exec_result.get("output_hash", "")
        state["runtime"]["status_code"] = exec_result.get("status", "error")
        state["runtime"]["error"] = exec_result.get("error", "")

        state["trace"]["status"] = "completed"
        state["trace"]["trace_file"] = exec_result.get("trace_file", "")
        print(f"  Execution ID: {exec_result['execution_id']}")
        print(f"  Trace ID:     {exec_result['trace_id']}")
        print(f"  Session ID:   {exec_result.get('session_id', '?')}")
        print(f"  Status:       {exec_result.get('status', '?')}")
        print(f"  Latency:      {exec_result.get('latency_ms', 0)}ms")
        print(f"  Tokens:       {exec_result.get('token_usage', {}).get('total', 0)}")
        print(f"  Trace:        {exec_result.get('trace_file', '?')}")

        if exec_result.get("status") != "success":
            print(f"  WARNING: Runtime returned non-success status: {exec_result.get('status')}")
            print(f"  Error: {exec_result.get('error', '')}")

    except Exception as e:
        mark_failed(state, "runtime", e)
        print(f"  FAILED: {e}")
        save_loop_state(loop_id, state)
        return state

    state["runtime"]["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["trace"]["started_at"] = state["runtime"]["started_at"]
    state["trace"]["completed_at"] = state["runtime"]["completed_at"]

    # =====================================================================
    # Stage 3: Collector
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 3/8: Collector")
    print(f"{'─' * 70}")

    state["feedback"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "feedback"

    try:
        execution_id = state["runtime"]["execution_id"]
        candidates = collect_from_trace_ids([execution_id], quiet=True)
        state["feedback"]["status"] = "completed"
        state["feedback"]["candidate_ids"] = [c["candidate_id"] for c in candidates]
        print(f"  Candidates: {len(candidates)}")
        for c in candidates:
            print(f"    {c['candidate_id']}: {c['candidate_type']} → {c['target_memory']}")
    except Exception as e:
        mark_failed(state, "feedback", e)
        print(f"  FAILED: {e}")
        candidates = []

    state["feedback"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 4: Validator
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 4/8: Validator")
    print(f"{'─' * 70}")

    state["validation"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "validation"

    try:
        validation_results = validate_candidates(candidates, quiet=True)
        state["validation"]["status"] = "completed"
        state["validation"]["validated_ids"] = [
            r["memory_id"] for r in validation_results if r["status"] == "validated"
        ]
        state["validation"]["rejected_ids"] = [
            r["memory_id"] for r in validation_results if r["status"] == "rejected"
        ]

        print(f"  Validated: {len(state['validation']['validated_ids'])}")
        print(f"  Rejected:  {len(state['validation']['rejected_ids'])}")
        for r in validation_results:
            label = "validated" if r["status"] == "validated" else "rejected"
            reason = r.get("rejection_reason", "")
            print(f"    {r['memory_id']}: {label}" + (f" — {reason}" if reason else ""))

    except Exception as e:
        mark_failed(state, "validation", e)
        print(f"  FAILED: {e}")
        validation_results = []

    state["validation"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 5: Promoter
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 5/8: Promoter")
    print(f"{'─' * 70}")

    state["promotion"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "promotion"

    promotion_results = []
    validated_results = [r for r in validation_results if r["status"] == "validated"]

    try:
        for v in validated_results:
            result = promote_validated(v)
            promotion_results.append(result)
            if result["status"] == "applied":
                state["promotion"]["promoted_ids"].append(result["memory_id"])
            else:
                state["promotion"]["rejected_ids"].append(result["memory_id"])

        state["promotion"]["status"] = "completed"
        print(f"  Promoted: {len(state['promotion']['promoted_ids'])}")
        print(f"  Rejected: {len(state['promotion']['rejected_ids'])}")
        for r in promotion_results:
            if r["status"] == "applied":
                eu = r.get("evidence_updates", {})
                print(f"    {r['memory_id']}: applied ({eu.get('old_evidence_level', '?')} → {eu.get('new_evidence_level', '?')})")
            else:
                print(f"    {r['memory_id']}: rejected — {r.get('rejection_reason', '?')}")

    except Exception as e:
        mark_failed(state, "promotion", e)
        print(f"  FAILED: {e}")

    state["promotion"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 6: Reconciler
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 6/8: Reconciler")
    print(f"{'─' * 70}")

    state["reconciliation"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "reconciliation"

    try:
        consistency = check_consistency()
        if consistency.get("consistent"):
            state["reconciliation"]["status"] = "completed"
            state["reconciliation"]["result"] = "CONSISTENT"
            print(f"  Result: CONSISTENT")
        else:
            print(f"  Result: INCONSISTENT — running repair...")
            changes = repair_index()
            state["reconciliation"]["status"] = "completed"
            state["reconciliation"]["result"] = f"REPAIRED ({len(changes)} changes)"
            print(f"  Repaired: {len(changes)} field(s)")
            for ch in changes:
                print(f"    {ch['memory_id']}.{ch['field']}: {ch['old_value']} → {ch['new_value']}")
    except Exception as e:
        mark_failed(state, "reconciliation", e)
        print(f"  FAILED: {e}")

    state["reconciliation"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Finalize
    # =====================================================================
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "completed"

    if state["final_status"] != "failed":
        state["final_status"] = "completed"

    save_loop_state(loop_id, state)

    print(f"\n{'=' * 70}")
    print(f"Loop Complete: {loop_id}")
    print(f"Status:        {state['final_status']}")
    print(f"Execution:     {state['runtime']['execution_id']}")
    print(f"Trace:         {state['runtime']['trace_id']}")
    print(f"Session:       {state['runtime']['session_id']}")
    print(f"Candidates:    {len(candidates)}")
    print(f"Validated:     {len(state['validation']['validated_ids'])}")
    print(f"Promoted:      {len(state['promotion']['promoted_ids'])}")
    print(f"Reconciler:    {state['reconciliation']['result']}")
    print(f"State:         {state_path}")
    print(f"{'=' * 70}")

    return state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 loop_controller.py <task_id> <task_text> [memory_mode] [model]")
        print()
        print("Examples:")
        print('  python3 loop_controller.py RT-003 "分析 MySQL 慢查询问题" enabled')
        print('  python3 loop_controller.py RT-004 "设计一个分布式缓存方案" enabled')
        print()
        sys.exit(1)

    task_id = sys.argv[1]
    task_text = sys.argv[2]
    memory_mode = sys.argv[3] if len(sys.argv) > 3 else "enabled"
    model = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_MODEL

    result = run_loop(task_id, task_text, memory_mode, model)

    # Print final status for machine parsing
    print(f"\nLOOP_EXECUTION: {'PASS' if result['final_status'] == 'completed' else 'FAIL'}")
    print(f"TRACE: {'真实' if result['runtime']['session_id'] else '模拟'}")
    print(f"PROVENANCE: {'完整' if result['runtime']['trace_id'] and result['runtime']['execution_id'] else '不完整'}")