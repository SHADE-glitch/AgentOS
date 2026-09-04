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
import json
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
from runtime_adapter import execute as runtime_execute, generate_loop_id, execute_with_reliability
from collector import collect_from_trace_ids, write_candidates_output, save_collector_state, load_collector_state
# Phase 8.2.1: TeamResult collector for multi-agent memory feedback loop
from team_result_collector import collect_from_team_results
# Phase 8.2.1.1: Memory resolver for bootstrapping new H-xxx hypotheses
from memory_resolver import resolve_candidates_targets
from file_utils import atomic_yaml_write, cleanup_old_files
from validator import validate_candidates
from promoter import promote_validated
from memory_state_reconciler import check_consistency, repair_index
from project_preflight import run_preflight
from code_validator import validate_code_changes

# Phase 8.9: Audit layer integration
sys.path.insert(0, os.path.join(BASE, "runtime", "audit"))
from audit_integration import (
    record_retrieval_audit,
    collect_task_evidence_before,
    collect_task_evidence_after,
    validate_team_result_claims,
    generate_provenance_artifact,
)

# Phase 10: Recovery loop integration
sys.path.insert(0, os.path.join(BASE, "runtime", "recovery"))
from recovery_integration import run_recovery_loop, run_recovery_loop_with_execution

# Phase 5.7: Real Router, Skill, Telemetry
from agent_router import route as router_route
from skill_loader import build_skill_context as skill_load
from telemetry_writer import (
    emit_task_event,
    emit_route_event,
    emit_memory_event,
    emit_skill_event,
    emit_execution_event,
    emit_validation_event,
    emit_outcome_event,
    emit_failure_event,
)

# Phase 7.4: Runtime Integration Hardening — Orchestrator + Collaboration
sys.path.insert(0, os.path.join(BASE, "runtime", "router"))
sys.path.insert(0, os.path.join(BASE, "runtime", "orchestrator"))
sys.path.insert(0, os.path.join(BASE, "runtime", "collaboration"))
from orchestrator import Orchestrator
from decision import DecisionContext
from task_decomposer import TaskDecomposer, decompose
from scheduler import Scheduler, create_real_executor
from aggregator import Aggregator, aggregate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_PROVIDER = os.environ.get("AOS_RUNTIME_PROVIDER", "opencode")
DEFAULT_MODEL = os.environ.get("AOS_RUNTIME_MODEL", "")
DEFAULT_RUNTIME_MODE = os.environ.get("AOS_RUNTIME_MODE", "REAL_HOST")  # Phase 5.7
EXECUTION_CONTRACT = os.path.join(LOOP_CONTROLLER_DIR, "execution-contract.yaml")


def load_contract():
    """Load the execution contract template."""
    if os.path.exists(EXECUTION_CONTRACT):
        with open(EXECUTION_CONTRACT) as f:
            return _safe_yaml_load(f)
    return {}


def _safe_yaml_load(file_or_path):
    """Safely load YAML. Phase 5.9: uses safe_load only (no unsafe_load)."""
    try:
        if isinstance(file_or_path, str):
            with open(file_or_path) as f:
                return yaml.safe_load(f)
        else:
            return yaml.safe_load(file_or_path)
    except Exception:
        return None


def save_loop_state(loop_id, state):
    """Save loop state to state/<loop_id>.yaml. Phase 5.9: atomic write."""
    path = os.path.join(STATE_DIR, f"{loop_id}.yaml")
    return atomic_yaml_write(path, state)


def load_loop_state(loop_id):
    """Load existing loop state if it exists."""
    path = os.path.join(STATE_DIR, f"{loop_id}.yaml")
    if os.path.exists(path):
        with open(path) as f:
            return _safe_yaml_load(f)


def init_loop_state(loop_id, task_id, task_text, memory_mode, model, provider, runtime_mode="REAL_HOST", session_id=""):
    """Initialize a fresh loop state from the execution contract."""
    contract = load_contract()
    loop_exec = contract.get("loop_execution", {}) if contract else {}

    state = {
        "loop_id": loop_id,
        "task_id": task_id,
        "task_text": task_text,
        "memory_mode": memory_mode,
        "model": model,
        "provider": provider,
        "runtime_mode": runtime_mode,
        "session_id": session_id,  # Phase 10.5: Unified session ID for audit/recovery
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

        "router": {
            "status": "pending",
            "intent": "",
            "lead_skill": "",
            "support_skills": [],
            "confidence": "",
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "skill": {
            "status": "pending",
            "lead_skill": "",
            "support_skills": [],
            "skills_loaded": [],
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
            "provider": provider,
            "model": model,
            "latency_ms": 0,
            "token_usage": {},
            "output_hash": "",
            "status_code": "",
            "error": "",
            "started_at": "",
            "completed_at": "",
            # Phase 8.2.1: executor metadata for multi-agent delegation
            "executor": {
                "type": "single-agent",
                "team_id": "",
            },
        },

        "trace": {
            "status": "pending",
            "trace_file": "",
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "telemetry": {
            "status": "pending",
            "events": [],
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
            "hypothesis_ids": [],  # Phase 8.2.1.1: H-xxx hypotheses tracked separately
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

        # Phase 10: Recovery loop state
        "recovery": {
            "status": "pending",
            "recovery_attempted": False,
            "recovery_success": False,
            "failures_detected": 0,
            "final_status": "skipped",
            "errors": [],
            "execution_result": None,
            "started_at": "",
            "completed_at": "",
        },

        # Phase 7.4: Orchestrator + Collaboration state
        "orchestrator": {
            "status": "pending",
            "team_id": "",
            "is_multi_agent": False,
            "lead_agent": "",
            "support_agents": [],
            "rules_applied": [],
            "pruned_roles": [],
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "collaboration": {
            "status": "pending",
            "team_id": "",
            "cards_total": 0,
            "cards_completed": 0,
            "cards_failed": 0,
            "team_status": "",
            "execution_order": [],
            "error": "",
            "started_at": "",
            "completed_at": "",
        },

        "errors": [],
    }
    return state


def mark_failed(state, stage, error, critical=True):
    """Mark a stage as failed and record the error.
    
    Args:
        state: pipeline state dict
        stage: stage name (e.g. "retrieval", "router", "runtime")
        error: exception or error message
        critical: if True, sets final_status to "failed"; if False, records as warning
    """
    state[stage]["status"] = "failed"
    state[stage]["error"] = str(error)
    state["errors"].append({"stage": stage, "error": str(error), "critical": critical})
    if critical:
        state["final_status"] = "failed"


def run_loop(task_id, task_text, memory_mode="enabled", model="", provider="opencode", project_root="", runtime_mode="REAL_HOST"):
    """
    Execute a single closed-loop pipeline.

    Args:
        task_id: str like "RT-003"
        task_text: str, the task description
        memory_mode: "enabled" | "fallback" | "disabled"
        model: str, provider-specific model identifier
        provider: str, runtime provider name (opencode, test_provider, ...)
        project_root: str, path to project root for code validation
        runtime_mode: "REAL_HOST" | "TEST_PROVIDER" (Phase 5.7)

    Returns:
        dict with loop_id, final_status, and all stage results
    """
    loop_id = generate_loop_id()
    session_id = (os.environ.get("AOS_SESSION_ID", "")
                  or datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S"))
    state = init_loop_state(loop_id, task_id, task_text, memory_mode, model, provider, runtime_mode, session_id=session_id)

    # Phase 10.5: Inject session_id into environment for subprocesses
    os.environ["AOS_SESSION_ID"] = session_id

    # Phase 5.9: Cleanup old state/trace files (idempotent, once per execution)
    cleanup_old_files(STATE_DIR, max_age_days=30)
    cleanup_old_files(os.path.join(BASE, "runtime", "traces"), max_age_days=30)

    # Read entry evidence metadata from AOS bootstrap
    entry_metadata_raw = os.environ.get("AOS_ENTRY_METADATA", "")
    if entry_metadata_raw:
        try:
            state["entry"] = json.loads(entry_metadata_raw)
        except json.JSONDecodeError:
            state["entry"] = {"entry_type": "unknown", "error": "invalid json"}
    else:
        state["entry"] = {"entry_type": "direct", "note": "no aos metadata"}

    # Pipeline timestamps for real trace (Phase 5.7: REAL timestamps)
    pipeline_timestamps = {
        "task_received": datetime.now(timezone.utc).isoformat(),
    }

    print("=" * 70)
    print(f"Phase 5.7 — Agent OS Runtime Pipeline (Closed Loop)")
    print(f"Loop ID:    {loop_id}")
    print(f"Task ID:    {task_id}")
    print(f"Task:       {task_text[:80]}")
    print(f"Memory:     {memory_mode}")
    print(f"Model:      {model}")
    print(f"Mode:       {runtime_mode}")
    print("=" * 70)

    # Save initial state
    state_path = save_loop_state(loop_id, state)
    print(f"\nLoop state: {state_path}")

    # Generate execution_id for telemetry correlation
    execution_id = f"EXEC-{int(time.time())}"

    # Phase 5.7: Emit task event
    state["telemetry"]["started_at"] = datetime.now(timezone.utc).isoformat()
    try:
        task_event = emit_task_event(execution_id, task_id, task_text, provider, model, runtime_mode)
        state["telemetry"]["events"].append("task")
    except Exception:
        pass

    # =====================================================================
    # Stage 1: Retrieval (Memory)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 1/10: Memory Retrieval")
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

        # Phase 8.9: Audit — record retrieval event
        try:
            record_retrieval_audit(
                query=decision_context.get("retrieval_raw", {}).get("query", {}),
                raw_result=decision_context.get("retrieval_raw", {}),
                decision_context=decision_context,
                task_id=task_id,
                loop_id=loop_id,
                session_id=session_id,
            )
        except Exception:
            pass  # Non-critical audit hook
    except Exception as e:
        mark_failed(state, "retrieval", e, critical=False)
        print(f"  FAILED: {e}")
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
    pipeline_timestamps["memory_retrieved"] = datetime.now(timezone.utc).isoformat()

    # Phase 5.7: Emit memory event
    try:
        emit_memory_event(execution_id, task_id, decision_context)
        state["telemetry"]["events"].append("memory")
    except Exception:
        pass

    # =====================================================================
    # Stage 2: Router (Phase 5.7 — REAL Router)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 2/10: Router")
    print(f"{'─' * 70}")

    state["router"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "router"

    try:
        route_decision = router_route(task_text, memory_context=decision_context)
        state["router"]["status"] = "completed"
        state["router"]["intent"] = route_decision.get("intent", "")
        state["router"]["lead_skill"] = route_decision.get("lead_skill", "")
        state["router"]["support_skills"] = route_decision.get("support_skills", [])
        state["router"]["confidence"] = route_decision.get("confidence", "")

        print(f"  Intent:       {state['router']['intent']}")
        print(f"  Lead Skill:   {state['router']['lead_skill']}")
        print(f"  Support:      {state['router']['support_skills']}")
        print(f"  Confidence:   {state['router']['confidence']}")
        print(f"  Mem Influence: {route_decision.get('memory_influence', 'none')}")
    except Exception as e:
        mark_failed(state, "router", e)
        print(f"  FAILED: {e}")
        route_decision = {
            "intent": "coding",
            "domains": ["backend"],
            "lead_skill": "backend-architect",
            "support_skills": [],
            "confidence": "low",
            "memory_influence": "none",
            "rules_applied": ["fallback routing"],
            "started_at": state["router"]["started_at"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    state["router"]["completed_at"] = datetime.now(timezone.utc).isoformat()
    pipeline_timestamps["routing_completed"] = datetime.now(timezone.utc).isoformat()

    # Phase 5.7: Emit route event
    try:
        emit_route_event(execution_id, task_id, route_decision)
        state["telemetry"]["events"].append("route")
    except Exception:
        pass

    # =====================================================================
    # Stage 3: Skill Loader (Phase 5.7 — REAL Skill loading)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 3/10: Skill Loader")
    print(f"{'─' * 70}")

    state["skill"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "skill"

    try:
        skill_context = skill_load(route_decision)
        state["skill"]["status"] = "completed"
        state["skill"]["lead_skill"] = skill_context.get("lead_skill", {}).get("name", "")
        state["skill"]["support_skills"] = [s.get("name", "") for s in skill_context.get("support_skills", [])]
        state["skill"]["skills_loaded"] = skill_context.get("skills_loaded", [])

        print(f"  Lead:    {state['skill']['lead_skill']}")
        print(f"  Support: {state['skill']['support_skills']}")
        print(f"  Loaded:  {state['skill']['skills_loaded']}")
    except Exception as e:
        mark_failed(state, "skill", e)
        print(f"  FAILED: {e}")
        skill_context = {
            "lead_skill": {"name": "backend-architect", "loaded": False},
            "support_skills": [],
            "skills_loaded": ["backend-architect"],
            "prompt_prefix": "You are acting as a Backend Architect.",
            "started_at": state["skill"]["started_at"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    state["skill"]["completed_at"] = datetime.now(timezone.utc).isoformat()
    pipeline_timestamps["skill_loaded"] = datetime.now(timezone.utc).isoformat()

    # Phase 5.7: Emit skill event
    try:
        emit_skill_event(execution_id, task_id, skill_context)
        state["telemetry"]["events"].append("skill")
    except Exception:
        pass

    # Attach classification to decision_context for runtime_adapter
    decision_context["classification"] = {
        "category": route_decision.get("intent", "backend"),
        "domains": route_decision.get("domains", []),
        "roles": [],
        "keywords": [],
        "difficulty": "medium",
    }

    # Phase 5.7: Attach real Router and Skill decisions to decision_context
    decision_context["route_decision"] = route_decision
    decision_context["skill_context"] = skill_context

    state["decision"]["status"] = "completed"
    state["decision"]["started_at"] = state["router"]["started_at"]
    state["decision"]["completed_at"] = state["skill"]["completed_at"]
    state["decision"]["influence"] = route_decision.get("memory_influence", "none")

    pipeline_timestamps["orchestration_completed"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 3.5: Orchestrator (Phase 7.4 — Team Formation)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 3.5/10: Orchestrator — Team Formation (Phase 7.4)")
    print(f"{'─' * 70}")

    state["orchestrator"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "orchestrator"

    # Build DecisionContext from Router output
    decision_ctx = DecisionContext(
        task_text=task_text,
        intent=route_decision.get("intent", "coding"),
        domains=route_decision.get("domains", ["backend"]),
        primary_domain=route_decision.get("primary_domain", route_decision.get("domains", ["backend"])[0]),
        lead_skill=route_decision.get("lead_skill", "backend-architect"),
        support_skills=route_decision.get("support_skills", []),
        confidence=route_decision.get("confidence", "medium"),
        difficulty=route_decision.get("difficulty", "medium"),
    )

    try:
        orch = Orchestrator()
        orch.load_rules()

        # Phase 7.4: Use should_form_team() to gate multi-agent path
        # This prevents false-positive team formation from Router's support_skills
        should_team = orch.should_form_team(decision_ctx)
        print(f"  Should form team: {should_team}")

        if should_team:
            team_plan = orch.form_team(task_text, decision_ctx)
            state["orchestrator"]["status"] = "completed"
            state["orchestrator"]["team_id"] = team_plan.team_id
            state["orchestrator"]["is_multi_agent"] = len(team_plan.support_agents) > 0
            state["orchestrator"]["lead_agent"] = team_plan.lead_agent
            state["orchestrator"]["support_agents"] = team_plan.support_agents
            state["orchestrator"]["rules_applied"] = team_plan.rules_applied
            state["orchestrator"]["pruned_roles"] = team_plan.pruned_roles

            print(f"  Team ID:      {team_plan.team_id}")
            print(f"  Lead:         {team_plan.lead_agent}")
            print(f"  Support:      {team_plan.support_agents}")
            print(f"  Multi-agent:  {state['orchestrator']['is_multi_agent']}")
            print(f"  Rules:        {team_plan.rules_applied}")
        else:
            # Single-agent: skip team formation
            team_plan = None
            state["orchestrator"]["status"] = "completed"
            state["orchestrator"]["is_multi_agent"] = False
            state["orchestrator"]["lead_agent"] = decision_ctx.lead_skill
            state["orchestrator"]["support_agents"] = []
            state["orchestrator"]["rules_applied"] = ["single-agent: no team needed"]
            print(f"  Single-agent: {decision_ctx.lead_skill} (no team needed)")
    except Exception as e:
        mark_failed(state, "orchestrator", e, critical=False)
        print(f"  FAILED: {e} — falling back to single-agent")
        team_plan = None
        state["orchestrator"]["status"] = "failed"
        state["orchestrator"]["error"] = str(e)
        state["orchestrator"]["is_multi_agent"] = False

    state["orchestrator"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 3.6: Collaboration Runtime (Phase 7.4 — Multi-Agent Execution)
    # =====================================================================
    is_multi_agent = state["orchestrator"]["is_multi_agent"] and team_plan is not None

    # Phase 10.5: Initialize team_result_data before branching (MINOR-1 fix)
    team_result_data = None

    if is_multi_agent:
        print(f"\n{'─' * 70}")
        print(f"Stage 3.6/10: Collaboration Runtime (Phase 7.4)")
        print(f"{'─' * 70}")

        state["collaboration"]["started_at"] = datetime.now(timezone.utc).isoformat()
        state["current_stage"] = "collaboration"

        try:
            # Step 1: Decompose TeamPlan into TaskCards
            task_cards = decompose(task_text, team_plan)
            state["collaboration"]["cards_total"] = len(task_cards)
            state["collaboration"]["team_id"] = team_plan.team_id
            print(f"  TaskCards:    {len(task_cards)}")
            for tc in task_cards:
                print(f"    {tc.task_id}: {tc.role} (deps: {tc.dependencies})")

            # Step 2: Create real agent executor using runtime_adapter
            # Phase 7.5: Pass timeout_seconds=900 for complex multi-agent tasks
            agent_executor = create_real_executor(
                runtime_execute_fn=execute_with_reliability,
                decision_context=decision_context,
                model=model,
                provider=provider,
                project_root=project_root,
                timeout_seconds=900,
            )

            # Step 3: Schedule and execute all TaskCards
            scheduler = Scheduler(agent_executor=agent_executor)
            schedule_result = scheduler.execute(task_cards, context={
                "task": task_text,
                "team_plan": team_plan,
                "decision_context": decision_ctx,
                "project_root": project_root,
            })

            # Step 4: Aggregate results
            completed_cards = schedule_result["completed"]
            failed_cards = schedule_result["failed"]
            aggregated = aggregate(schedule_result["cards"])

            state["collaboration"]["status"] = "completed"
            state["collaboration"]["cards_completed"] = len(completed_cards)
            state["collaboration"]["cards_failed"] = len(failed_cards)
            state["collaboration"]["team_status"] = aggregated.status
            state["collaboration"]["execution_order"] = schedule_result["execution_order"]

            print(f"  Completed:    {len(completed_cards)}")
            print(f"  Failed:       {len(failed_cards)}")
            print(f"  Team Status:  {aggregated.status}")
            print(f"  Exec Order:   {schedule_result['execution_order']}")

            # Phase 7.5: Persist TeamResult to file
            team_result_path = os.path.join(
                os.path.dirname(STATE_DIR),
                "validation",
                f"team-result-{loop_id}.yaml"
            )
            team_result_data = {
                "loop_id": loop_id,
                "team_id": team_plan.team_id,
                "team_result": aggregated.to_dict() if hasattr(aggregated, 'to_dict') else {},
                "hypotheses_injected": state.get("retrieval", {}).get("hypotheses", []),
                "task_cards": [
                    {
                        "task_id": tc.task_id,
                        "role": tc.role,
                        "status": tc.status,
                        "output_summary": tc.output_data.get("summary", "") if tc.output_data else "",
                        "output_len": len(tc.output_data.get("output", "")) if tc.output_data else 0,
                        "latency_ms": tc.output_data.get("latency_ms", 0) if tc.output_data else 0,
                    }
                    for tc in schedule_result["cards"]
                ],
                "execution_order": schedule_result["execution_order"],
                "completed_count": len(completed_cards),
                "failed_count": len(failed_cards),
            }
            os.makedirs(os.path.dirname(team_result_path), exist_ok=True)
            atomic_yaml_write(team_result_path, team_result_data)
            print(f"  TeamResult saved to: {team_result_path}")

            # Phase 8.9: Audit — validate TeamResult claims
            try:
                validate_team_result_claims(
                    team_result=team_result_data,
                    task_id=task_id,
                    loop_id=loop_id,
                    session_id=session_id,
                )
            except Exception:
                pass  # Non-critical

            # Phase 10.5 (M-1): Generate provenance artifact
            try:
                generate_provenance_artifact(
                    task_id=task_id,
                    loop_id=loop_id,
                    project_root=project_root,
                    session_id=session_id,
                )
            except Exception:
                pass  # Non-critical

            # Store collaboration result for subsequent stages
            exec_result = {
                "execution_id": f"TEAM-{team_plan.team_id}",
                "trace_id": f"TRACE-TEAM-{team_plan.team_id}",
                "session_id": "",
                "latency_ms": 0,
                "token_usage": {"total": 0, "input": 0, "output": 0},
                "output_hash": "",
                "status": aggregated.status if aggregated.status == "success" else "partial",
                "error": "",
                "trace_file": "",
                "is_multi_agent": True,
                "team_result": aggregated.to_dict() if hasattr(aggregated, 'to_dict') else {},
            }
            print(f"  Multi-agent collaboration complete. Skipping single-agent Stage 4.")

        except Exception as e:
            mark_failed(state, "collaboration", e, critical=True)
            print(f"  FAILED: {e}")
            state["collaboration"]["status"] = "failed"
            state["collaboration"]["error"] = str(e)
            save_loop_state(loop_id, state)
            return state

        state["collaboration"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        pipeline_timestamps["collaboration_completed"] = datetime.now(timezone.utc).isoformat()

        # Skip Stage 4 (single-agent Runtime) — collaboration already executed
        print(f"\n  Stage 4/10: Runtime — DELEGATED (multi-agent collaboration)")
        state["runtime"]["status"] = "delegated"
        state["runtime"]["execution_id"] = exec_result["execution_id"]
        state["runtime"]["trace_id"] = exec_result["trace_id"]
        state["runtime"]["status_code"] = exec_result["status"]
        state["runtime"]["started_at"] = state["collaboration"]["started_at"]
        state["runtime"]["completed_at"] = state["collaboration"]["completed_at"]
        # Phase 8.2.1: executor metadata for multi-agent delegation
        state["runtime"]["executor"] = {
            "type": "multi-agent",
            "team_id": team_plan.team_id,
        }
        state["trace"]["status"] = "completed"
        state["trace"]["trace_file"] = ""
        pipeline_timestamps["agent_started"] = state["collaboration"]["started_at"]
        pipeline_timestamps["agent_completed"] = state["collaboration"]["completed_at"]

        # Jump to Stage 5 (Code Validation)
        # ─ continue below Stage 4 block ─

    else:
        # Single-agent: proceed to Stage 4 (Runtime) as before
        state["collaboration"]["status"] = "skipped"
        state["collaboration"]["error"] = "single_agent"

    if not is_multi_agent:
        # =====================================================================
        # Stage 4: Runtime (includes Provider execution)
        # =====================================================================
        print(f"\n{'─' * 70}")
        print(f"Stage 4/10: Runtime ({provider})")
        print(f"{'─' * 70}")

        state["runtime"]["started_at"] = datetime.now(timezone.utc).isoformat()
        state["current_stage"] = "runtime"
        pipeline_timestamps["agent_started"] = datetime.now(timezone.utc).isoformat()

        # Attach entry metadata to decision_context for trace (Phase 8.5-T2: loop_id provenance)
        decision_context["entry_metadata"] = state.get("entry", {})
        decision_context["loop_id"] = loop_id

        # Phase 8.9: Audit — collect pre-task evidence
        before_evidence = {}
        try:
            before_evidence = collect_task_evidence_before(
                task_id=task_id, project_root=project_root, loop_id=loop_id, session_id=session_id
            )
        except Exception:
            pass  # Non-critical

        try:
            exec_result = runtime_execute(task_id, task_text, decision_context, model=model, provider=provider, pipeline_timestamps=pipeline_timestamps, project_root=project_root, loop_id=loop_id)
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

            # Phase 8.9: Audit — collect post-task evidence
            try:
                collect_task_evidence_after(
                    task_id=task_id,
                    before_evidence=before_evidence,
                    project_root=project_root,
                    loop_id=loop_id,
                    test_command=exec_result.get("test_command", ""),
                    test_stdout=exec_result.get("test_stdout", ""),
                    test_stderr=exec_result.get("test_stderr", ""),
                    test_exit_code=exec_result.get("test_exit_code"),
                    session_id=session_id,
                )
            except Exception:
                pass  # Non-critical

            # Phase 10.5: Generate minimal TeamResult for single-agent path (M-3 fix)
            team_result_data = {
                "agent": provider,
                "task_id": task_id,
                "loop_id": loop_id,
                "summary": exec_result.get("output", "")[:500] if exec_result.get("output") else "",
                "evidence": f"evidence-{task_id}.json",
                "validation_context": decision_context.get("task_classification", ""),
                "model": model,
                "provider": provider,
                "execution_id": exec_result.get("execution_id", ""),
                "trace_id": exec_result.get("trace_id", ""),
                "status": exec_result.get("status", "unknown"),
                "latency_ms": exec_result.get("latency_ms", 0),
                "token_usage": exec_result.get("token_usage", {}),
            }
            state["collaboration"]["team_status"] = exec_result.get("status", "unknown")

            # Phase 8.9: Validate single-agent TeamResult
            try:
                validate_team_result_claims(
                    team_result=team_result_data,
                    task_id=task_id,
                    loop_id=loop_id,
                    session_id=session_id,
                )
            except Exception:
                pass  # Non-critical

            # Phase 10.5 (M-1): Generate provenance artifact
            try:
                generate_provenance_artifact(
                    task_id=task_id,
                    loop_id=loop_id,
                    project_root=project_root,
                    session_id=session_id,
                )
            except Exception:
                pass  # Non-critical

        except Exception as e:
            mark_failed(state, "runtime", e)
            print(f"  FAILED: {e}")
            # Phase 5.7: Emit failure event
            try:
                emit_failure_event(execution_id, task_id, "runtime", str(e))
                state["telemetry"]["events"].append("failure")
            except Exception:
                pass
            save_loop_state(loop_id, state)
            return state

        state["runtime"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["trace"]["started_at"] = state["runtime"]["started_at"]
        state["trace"]["completed_at"] = state["runtime"]["completed_at"]
        pipeline_timestamps["agent_completed"] = datetime.now(timezone.utc).isoformat()

        # Phase 5.7: Emit execution event
        try:
            emit_execution_event(execution_id, task_id, exec_result)
            state["telemetry"]["events"].append("execution")
        except Exception:
            pass

    # =====================================================================
    # Stage 5: Code Validation (Phase 6.2)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 5/10: Code Validation (Phase 6.2)")
    print(f"{'─' * 70}")

    state["code_validation"] = {
        "status": "pending",
        "validation_status": "",
        "build_after": "",
        "test_after": "",
        "files_changed": 0,
        "unexpected_files": 0,
        "error": "",
        "started_at": "",
        "completed_at": "",
    }
    state["code_validation"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "code_validation"

    # Get project root from entry metadata, decision context, or parameter
    if not project_root:
        entry = state.get("entry", {})
        if entry:
            project_root = entry.get("working_directory", "")
    if not project_root:
        project_root = decision_context.get("working_directory", "")
    if not project_root:
        project_root = os.environ.get("AOS_PROJECT_ROOT", "")

    if project_root:
        try:
            # Run project preflight
            print(f"  Project root: {project_root}")
            preflight = run_preflight(project_root)
            print(f"  Preflight status: {preflight.status}")
            print(f"  Build system: {preflight.build_system}")

            # Get expected files from task context
            expected_files = decision_context.get("expected_files", [])

            # Run code validation
            code_result = validate_code_changes(
                execution_id=exec_result["execution_id"],
                project_root=project_root,
                expected_files=expected_files,
                compile_command=preflight.compile_command,
                test_command=preflight.test_command,
            )

            state["code_validation"]["status"] = "completed"
            state["code_validation"]["validation_status"] = code_result.validation_status
            state["code_validation"]["build_after"] = code_result.build_after.status
            state["code_validation"]["test_after"] = code_result.test_after.status
            state["code_validation"]["files_changed"] = len(code_result.files_changed)
            state["code_validation"]["unexpected_files"] = code_result.unexpected_files_changed

            print(f"  Validation status: {code_result.validation_status}")
            print(f"  Build: {code_result.build_after.status}")
            print(f"  Test: {code_result.test_after.status}")
            print(f"  Files changed: {len(code_result.files_changed)}")
            print(f"  Unexpected files: {code_result.unexpected_files_changed}")

            # Store code validation result for trace
            state["code_validation"]["result"] = code_result

            # Update trace file with validation results
            trace_file = exec_result.get("trace_file", "")
            if trace_file and os.path.exists(trace_file):
                try:
                    trace_data = _safe_yaml_load(trace_file)
                    if trace_data:
                        from dataclasses import asdict
                        trace_data["code_validation"] = {
                            "status": code_result.validation_status,
                            "validated_at": code_result.validated_at,
                            "git_clean_before": code_result.git_clean_before,
                            "git_clean_after": code_result.git_clean_after,
                            "files_changed": len(code_result.files_changed),
                            "expected_files_changed": code_result.expected_files_changed,
                            "unexpected_files_changed": code_result.unexpected_files_changed,
                            "only_expected_change": code_result.only_expected_change,
                            "build_before": code_result.build_before.status,
                            "build_after": code_result.build_after.status,
                            "build_degradation": code_result.build_degradation,
                            "test_before": code_result.test_before.status,
                            "test_after": code_result.test_after.status,
                            "test_degradation": code_result.test_degradation,
                            "validation_checks": code_result.validation_checks,
                        }
                        if "evidence" in trace_data and "verification" in trace_data["evidence"]:
                            trace_data["evidence"]["verification"].append(
                                f"Code Validation: {code_result.validation_status} "
                                f"(build={code_result.build_after.status}, "
                                f"test={code_result.test_after.status}, "
                                f"files={len(code_result.files_changed)})"
                            )
                        # Phase 5.9: Atomic write for trace update
                        header_lines = [
                            f"# Execution Trace — {task_id} (Memory {'ON' if decision_context.get('retrieved') else 'OFF'})",
                            f"# Phase 6.2 — Runtime Reliability Validation",
                            f"# Generated: {datetime.now(timezone.utc).isoformat()}",
                            f"# Provider: {provider}",
                        ]
                        atomic_yaml_write(trace_file, trace_data, header_lines=header_lines)
                        print(f"  Trace updated with validation results")
                except Exception as e:
                    print(f"  WARNING: Failed to update trace: {e}")

        except Exception as e:
            mark_failed(state, "code_validation", e)
            print(f"  FAILED: {e}")
    else:
        print(f"  SKIPPED: No project root available")
        state["code_validation"]["status"] = "skipped"
        state["code_validation"]["error"] = "No project root available"

    state["code_validation"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 6: Collector
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 6/10: Collector")
    print(f"{'─' * 70}")

    state["feedback"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "feedback"

    try:
        execution_id = state["runtime"]["execution_id"]
        # Phase 8.2.1: Multi-agent → TeamResultCollector (closes memory feedback loop)
        if state["runtime"].get("executor", {}).get("type") == "multi-agent":
            # Use TeamResultCollector to extract candidates from team-result YAML
            loop_id_for_collector = loop_id
            candidates = collect_from_team_results([loop_id_for_collector], quiet=True)
            print(f"  Multi-agent TeamResult collector: {len(candidates)} candidates")
            if not candidates:
                print(f"  (No candidates extracted — this is expected if no patterns matched)")
        else:
            # Phase 5.10: Collect candidates without updating state yet
            candidates = collect_from_trace_ids([execution_id], quiet=True, update_state=False, loop_id=loop_id)
        
        # Write candidates to memory-candidates.yaml (append to existing)
        if candidates:
            # Load existing candidates and merge
            existing_file = "/home/shade/.agents/runtime/memory-feedback/memory-candidates.yaml"
            existing_candidates = []
            source_executions = []
            if os.path.exists(existing_file):
                with open(existing_file) as f:
                    existing_data = yaml.safe_load(f) or {}
                    existing_candidates = existing_data.get("candidates", [])
                    source_executions = existing_data.get("source_executions", [])
            
            # Merge new candidates (avoid duplicates by candidate_id)
            existing_ids = {c["candidate_id"] for c in existing_candidates}
            new_candidates = [c for c in candidates if c["candidate_id"] not in existing_ids]
            all_candidates = existing_candidates + new_candidates
            
            # Update source executions
            new_eids = list(set(c.get("source_execution", "") for c in new_candidates))
            source_executions = list(set(source_executions + new_eids))
            
            # Write merged candidates
            write_candidates_output(all_candidates, source_executions, loop_id=loop_id)
            
            # Now update collector state (mark traces as processed)
            state_data = load_collector_state()
            state_data["processed_traces"].append({
                "trace_id": execution_id,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "candidates_generated": len(candidates),
            })
            save_collector_state(state_data)
        
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
    # Stage 6.5: Memory Resolution (Phase 8.2.1.1)
    # =====================================================================
    # Resolve P8-xxx → H-xxx for candidates targeting non-existent memory IDs.
    # Auto-bootstraps hypothesis entries in retrieval-index.yaml.
    if candidates:
        original_count = len(candidates)
        candidates = resolve_candidates_targets(candidates)
        resolved_count = sum(1 for c in candidates if c.get("resolved_from"))
        if resolved_count > 0:
            print(f"  Memory Resolver: {resolved_count}/{original_count} candidates bootstrapped → H-xxx hypotheses")
            for c in candidates:
                if c.get("resolved_from"):
                    print(f"    {c['resolved_from']} → {c['target_memory']}")

    # =====================================================================
    # Stage 7: Validator
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 7/10: Validator")
    print(f"{'─' * 70}")

    state["validation"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "validation"

    try:
        validation_results = validate_candidates(candidates, quiet=True, loop_id=loop_id)
        state["validation"]["status"] = "completed"
        state["validation"]["validated_ids"] = [
            r["memory_id"] for r in validation_results if r["status"] == "validated"
        ]
        state["validation"]["hypothesis_ids"] = [
            r["memory_id"] for r in validation_results if r["status"] == "hypothesis"
        ]
        state["validation"]["rejected_ids"] = [
            r["memory_id"] for r in validation_results if r["status"] == "rejected"
        ]

        print(f"  Validated:  {len(state['validation']['validated_ids'])}")
        print(f"  Hypothesis: {len(state['validation']['hypothesis_ids'])}")
        print(f"  Rejected:   {len(state['validation']['rejected_ids'])}")
        for r in validation_results:
            label = r["status"]
            reason = r.get("rejection_reason", "")
            print(f"    {r['memory_id']}: {label}" + (f" — {reason}" if reason else ""))

    except Exception as e:
        mark_failed(state, "validation", e)
        print(f"  FAILED: {e}")
        validation_results = []

    state["validation"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 8: Promoter
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 8/10: Promoter")
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
    # Stage 9: Reconciler
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 9/10: Reconciler")
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
    # Stage 9.5: Recovery Loop (Phase 11 — Semi-Autonomous Recovery)
    # =====================================================================
    print(f"\n{'─' * 70}")
    print(f"Stage 9.5/10: Recovery Loop (Phase 11)")
    print(f"{'─' * 70}")

    state["recovery"]["started_at"] = datetime.now(timezone.utc).isoformat()
    state["recovery"]["status"] = "running"

    try:
        # Phase 11: Use execution bridge (detect → plan → execute → verify)
        # runtime_execute is the runtime_adapter.execute function
        recovery_result = run_recovery_loop_with_execution(
            task_id=task_id,
            loop_id=loop_id,
            state=state,
            exec_result=exec_result if is_multi_agent else state.get("runtime", {}),
            team_result=team_result_data,
            decision_context=decision_context,
            runtime_executor=runtime_execute,  # Phase 11: delegate to OpenCode
            retry_context={"project_root": project_root},
            session_id=session_id,
        )
        state["recovery"]["status"] = "completed"
        state["recovery"]["recovery_attempted"] = recovery_result.get("recovery_attempted", False)
        state["recovery"]["recovery_success"] = recovery_result.get("recovery_success", False)
        state["recovery"]["failures_detected"] = recovery_result.get("failures_detected", 0)
        state["recovery"]["final_status"] = recovery_result.get("final_status", "completed")
        state["recovery"]["execution_result"] = recovery_result.get("execution_result")

        print(f"  Failures:     {state['recovery']['failures_detected']}")
        print(f"  Attempted:    {state['recovery']['recovery_attempted']}")
        print(f"  Success:      {state['recovery']['recovery_success']}")
        print(f"  Final Status: {state['recovery']['final_status']}")

        # If recovery detected critical failures and could not recover, mark as partial
        if recovery_result.get("failures_detected", 0) > 0 and not recovery_result.get("recovery_success", False):
            if state["final_status"] != "failed":
                state["final_status"] = "partial"
    except Exception as e:
        state["recovery"]["status"] = "failed"
        state["recovery"]["error"] = str(e)
        state["recovery"]["errors"].append(str(e))
        print(f"  FAILED: {e} (non-critical, pipeline continues)")

    state["recovery"]["completed_at"] = datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # Stage 10: Finalize & Telemetry
    # =====================================================================
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["current_stage"] = "completed"

    if state["final_status"] != "failed":
        state["final_status"] = "completed"

    # Phase 5.7: Emit validation and outcome events
    state["telemetry"]["completed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        emit_validation_event(execution_id, task_id, {"validation_status": state["final_status"]})
        state["telemetry"]["events"].append("validation")
    except Exception:
        pass

    try:
        outcome_summary = {
            "router": state["router"]["status"],
            "skill": state["skill"]["status"],
            "runtime": state["runtime"]["status_code"],
            "telemetry_events": len(state["telemetry"]["events"]),
        }
        emit_outcome_event(execution_id, task_id, state["final_status"], outcome_summary)
        state["telemetry"]["events"].append("outcome")
        state["telemetry"]["status"] = "completed"
    except Exception:
        pass

    save_loop_state(loop_id, state)

    print(f"\n{'=' * 70}")
    print(f"Loop Complete: {loop_id}")
    print(f"Status:        {state['final_status']}")
    print(f"Execution:     {state['runtime']['execution_id']}")
    print(f"Trace:         {state['runtime']['trace_id']}")
    print(f"Session:       {state['runtime']['session_id']}")
    print(f"Router:        {state['router']['lead_skill']} ({state['router']['confidence']})")
    print(f"Skill:         {state['skill']['skills_loaded']}")
    print(f"Telemetry:     {len(state['telemetry']['events'])} events")
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
        print("Usage: python3 loop_controller.py <task_id> <task_text> [memory_mode] [model] [provider] [runtime_mode]")
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
    provider = sys.argv[5] if len(sys.argv) > 5 else DEFAULT_PROVIDER
    runtime_mode = sys.argv[6] if len(sys.argv) > 6 else DEFAULT_RUNTIME_MODE

    result = run_loop(task_id, task_text, memory_mode, model, provider, runtime_mode=runtime_mode)

    # Print final status for machine parsing
    print(f"\nLOOP_EXECUTION: {'PASS' if result['final_status'] == 'completed' else 'FAIL'}")
    # Phase 7.5: Multi-agent collaboration has real execution but no single session_id
    is_multi = result.get("collaboration", {}).get("status") == "completed"
    has_session = bool(result['runtime'].get('session_id'))
    print(f"TRACE: {'真实 (multi-agent)' if is_multi else '真实' if has_session else '模拟'}")
    print(f"PROVENANCE: {'完整' if (result['runtime']['trace_id'] and result['runtime']['execution_id']) or is_multi else '不完整'}")