#!/usr/bin/env python3
"""
OpenCode Governance Bridge — Agent OS Runtime Entry (Host Integration)

Wires a Native OpenCode session into the EXISTING Agent OS runtime pipeline
WITHOUT spawning a second OpenCode instance and WITHOUT blocking the
interactive OpenCode session for minutes.

Architecture (single executor — OpenCode is the one and only tool executor):

  OpenCode user message
    ↓
  Host Plugin (index.ts)  ──preflight──▶  governance_bridge.py --preflight
    ↓                                          │ 1. create AOS session + loop_id
    │                                          │ 2. retrieval_adapt (memory subsystem)
    │                                          │ 3. agent_router.route → HybridRouter
    │                                          │ 4. skill_loader (role context)
    │                                          │ 5. collect_task_evidence_before
    │                                          │ 6. record_retrieval_audit
    │                                          │ 7. persist loop state
    ↓                                          └─ returns governance context
  OpenCode executes natively (Read/Edit/Grep/Shell)
    ↓
  Host Plugin  ──postflight──▶  governance_bridge.py --postflight
                                     │ 1. collect_task_evidence_after
                                     │ 2. detect_failures + plan recovery
                                     │ 3. finalize loop state
                                     └─ returns evidence/recovery result

CRITICAL CONSTRAINTS (per required architecture):
  - Does NOT call runtime_adapter.execute → no `opencode run --pure`.
  - Does NOT re-implement router/memory/evidence/recovery. Reuses existing runtime.
  - Runtime stage is marked `host_delegated` because OpenCode itself is the executor.
  - Fails open: on any error, returns a minimal context and never blocks the host.
"""

import os
import sys
import json
import uuid
import time
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
LOOP_DIR = os.path.join(BASE, "runtime", "loop-controller")
STATE_DIR = os.path.join(LOOP_DIR, "state")
ROUTER_DIR = os.path.join(BASE, "runtime")  # parent of router/ — needed for `from router.router import`
AUDIT_DIR = os.path.join(BASE, "runtime", "audit")
RECOVERY_DIR = os.path.join(BASE, "runtime", "recovery")

for _p in (LOOP_DIR, ROUTER_DIR, AUDIT_DIR, RECOVERY_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RECURSION_ENV = "AOS_HOST_PLUGIN_ACTIVE"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _uuid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def generate_loop_id():
    """Unique loop id (second precision + random suffix to avoid collisions)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"LOOP-{ts}-{uuid.uuid4().hex[:4].upper()}"


def generate_execution_id():
    return f"EXEC-{int(time.time())}"


def _atomic_yaml_write(path, data):
    import tempfile
    import yaml
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
        return path
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _emit(telemetry_writer, name, *args):
    fn = getattr(telemetry_writer, name, None)
    if fn is None:
        return
    try:
        return fn(*args)
    except Exception:
        return None


def build_governance_context(preflight: dict) -> str:
    """Render the governance context injected into the OpenCode system prompt."""
    lines = []
    lines.append("")
    lines.append("## Agent OS Runtime Context (governance layer)")
    lines.append("")

    cls = preflight.get("classification", {})
    if cls:
        parts = []
        if cls.get("category"):
            parts.append(f"category={cls['category']}")
        if cls.get("difficulty"):
            parts.append(f"difficulty={cls['difficulty']}")
        if parts:
            lines.append("Task: " + " | ".join(parts))

    router = preflight.get("router", {})
    if router.get("lead_skill"):
        lines.append(f"Lead role: {router['lead_skill']}")
        if router.get("support_skills"):
            lines.append(f"Support roles: {', '.join(router['support_skills'])}")

    mem = preflight.get("memory", {})
    if mem.get("retrieved", 0) > 0:
        lines.append(f"Relevant memories: {mem['retrieved']}")
        for m in mem.get("memories", [])[:3]:
            mid = m.get("memory_id", "?")
            content = (m.get("content") or "").strip()
            lines.append(f"  - {mid}: {content[:120]}")

    skill = preflight.get("skill", {})
    if skill.get("skills_loaded"):
        lines.append(f"Skills loaded: {', '.join(skill['skills_loaded'])}")

    for w in preflight.get("warnings", []):
        lines.append(f"⚠ {w}")

    lines.append("")
    lines.append(
        "Agent OS runs as a governance/runtime layer. You remain the single "
        "tool executor (Read/Edit/Grep/Shell). Use the routing/memory context "
        "above to inform your approach."
    )
    lines.append("")
    return "\n".join(lines)


# ── Preflight ─────────────────────────────────────────────────────

def run_preflight(task_text, session_id, cwd):
    from retrieval_adapter import adapt as retrieval_adapt, classify_task
    from agent_router import route as router_route
    from skill_loader import build_skill_context as skill_load
    from audit_integration import (
        record_retrieval_audit,
        collect_task_evidence_before,
    )
    from telemetry_writer import (
        emit_task_event,
        emit_route_event,
        emit_memory_event,
        emit_skill_event,
    )

    loop_id = generate_loop_id()
    task_id = _uuid("HOST")
    execution_id = generate_execution_id()

    aos_session = session_id or datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S")
    # Stable mapping: OpenCode session → AOS session (env + artifact)
    os.environ["AOS_SESSION_ID"] = aos_session

    state = {
        "loop_id": loop_id,
        "task_id": task_id,
        "task_text": task_text,
        "session_id": aos_session,
        "provider": os.environ.get("AOS_RUNTIME_PROVIDER", "opencode"),
        "model": os.environ.get("AOS_RUNTIME_MODEL", ""),
        "runtime_mode": "HOST_DELEGATED",
        "started_at": _now_iso(),
        "current_stage": "preflight",
        "final_status": "pending",
    }

    # Stage 1 — Memory retrieval (real memory subsystem)
    decision_context = retrieval_adapt(task_id, task_text, "enabled")
    memories = decision_context.get("memories", [])
    hypotheses = decision_context.get("hypotheses", [])
    state["retrieval"] = {
        "status": "completed",
        "retrieved_count": decision_context.get("total_retrieved", 0),
        "memory_ids": decision_context.get("ranking", []),
        "hypotheses": [h.get("memory_id", "") for h in hypotheses],
    }

    try:
        record_retrieval_audit(
            query=decision_context.get("retrieval_raw", {}).get("query", {}),
            raw_result=decision_context.get("retrieval_raw", {}),
            decision_context=decision_context,
            task_id=task_id,
            loop_id=loop_id,
            session_id=aos_session,
        )
    except Exception:
        pass

    _emit(emit_memory_event, execution_id, task_id, decision_context)

    # Stage 2 — HybridRouter (real routing decision + artifact)
    route_decision = router_route(task_text, memory_context=decision_context)
    state["router"] = {
        "status": "completed",
        "intent": route_decision.get("intent", ""),
        "lead_skill": route_decision.get("lead_skill", ""),
        "support_skills": route_decision.get("support_skills", []),
        "confidence": route_decision.get("confidence", ""),
        "artifact": route_decision.get("artifact", {}),
    }
    _emit(emit_route_event, execution_id, task_id, route_decision)

    # Stage 3 — Skill loader (real role context)
    skill_context = skill_load(route_decision)
    state["skill"] = {
        "status": "completed",
        "lead_skill": skill_context.get("lead_skill", {}).get("name", ""),
        "support_skills": [s.get("name", "") for s in skill_context.get("support_skills", [])],
        "skills_loaded": skill_context.get("skills_loaded", []),
    }
    _emit(emit_skill_event, execution_id, task_id, skill_context)

    _emit(emit_task_event, execution_id, task_id, task_text, state["provider"], state["model"], state["runtime_mode"])

    # Stage 4 — Evidence before (real git snapshot)
    state["evidence_before"] = {}
    try:
        state["evidence_before"] = collect_task_evidence_before(
            task_id=task_id,
            project_root=cwd,
            loop_id=loop_id,
            session_id=aos_session,
        )
    except Exception:
        pass

    state["evidence_before_path"] = state["evidence_before"].get("project_root", "") if state["evidence_before"] else ""

    # Persist loop state
    _atomic_yaml_write(os.path.join(STATE_DIR, f"{loop_id}.yaml"), state)

    classification = classify_task(task_text)

    preflight = {
        "task_id": task_id,
        "loop_id": loop_id,
        "session_id": aos_session,
        "aos_status": "completed",
        "classification": classification,
        "router": {
            "intent": route_decision.get("intent", ""),
            "lead_skill": route_decision.get("lead_skill", ""),
            "support_skills": route_decision.get("support_skills", []),
            "confidence": route_decision.get("confidence", ""),
        },
        "memory": {
            "retrieved": decision_context.get("total_retrieved", 0),
            "memories": memories,
            "hypotheses": hypotheses,
        },
        "skill": {
            "lead_skill": skill_context.get("lead_skill", {}).get("name", ""),
            "support_skills": [s.get("name", "") for s in skill_context.get("support_skills", [])],
            "skills_loaded": skill_context.get("skills_loaded", []),
        },
        "warnings": [],
        "artifacts": {
            "loop_state": os.path.join(STATE_DIR, f"{loop_id}.yaml"),
        },
    }

    return preflight


# ── Postflight ────────────────────────────────────────────────────

def run_postflight(task_id, loop_id, session_id, cwd):
    from audit_integration import collect_task_evidence_after
    from evidence_collector import collect_before as _before  # noqa: F401
    from failure_detector import detect_failures
    from recovery_planner import plan_recovery
    from retry_controller import get_retry_count

    aos_session = session_id or os.environ.get("AOS_SESSION_ID", "")
    os.environ["AOS_SESSION_ID"] = aos_session

    # Load loop state
    state_path = os.path.join(STATE_DIR, f"{loop_id}.yaml")
    import yaml
    state = {}
    if os.path.exists(state_path):
        try:
            state = yaml.safe_load(open(state_path)) or {}
        except Exception:
            state = {}

    before = state.get("evidence_before", {})

    evidence_path = ""
    try:
        after = collect_task_evidence_after(
            task_id=task_id,
            before_evidence=before,
            project_root=cwd,
            loop_id=loop_id,
            session_id=aos_session,
        )
        if after:
            evidence_path = after
    except Exception:
        evidence_path = ""

    # Failure detection → recovery plan (read-only decision, no auto retry)
    runtime_result = {
        "status": "completed",
        "task_id": task_id,
        "loop_id": loop_id,
    }
    failures = detect_failures(
        task_id=task_id,
        loop_id=loop_id,
        session_id=aos_session,
        runtime_result=runtime_result,
    )

    recovery = {
        "failures_detected": len(failures),
        "recovery_attempted": False,
        "recovery_success": False,
        "final_status": "completed",
        "plan": None,
    }

    if failures:
        retry_count = get_retry_count(task_id, session_id=aos_session)
        plan = plan_recovery(failures, task_id=task_id, loop_id=loop_id, retry_count=retry_count)
        recovery["plan"] = plan
        recovery["final_status"] = "partial"

    # Finalize loop state
    state["current_stage"] = "postflight"
    state["completed_at"] = _now_iso()
    state["final_status"] = "partial" if failures else "completed"
    state["evidence_after_path"] = evidence_path
    state["recovery"] = recovery
    _atomic_yaml_write(state_path, state)

    return {
        "task_id": task_id,
        "loop_id": loop_id,
        "session_id": aos_session,
        "aos_status": "completed",
        "evidence_path": evidence_path,
        "recovery": recovery,
        "final_status": state["final_status"],
    }


# ── CLI ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("usage: governance_bridge.py --preflight|--postflight --task JSON", file=sys.stderr)
        sys.exit(2)

    mode = sys.argv[1]
    args = sys.argv[2:]

    payload = {}
    if "--payload" in args:
        i = args.index("--payload")
        try:
            payload = json.loads(args[i + 1])
        except (IndexError, json.JSONDecodeError):
            payload = {}

    task_text = payload.get("task", "")
    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", os.getcwd())
    task_id = payload.get("task_id", "")
    loop_id = payload.get("loop_id", "")

    if mode == "--preflight":
        if not task_text:
            print(json.dumps({"aos_status": "fallback", "reason": "no task"}, ensure_ascii=False))
            sys.exit(0)
        result = run_preflight(task_text, session_id, cwd)

    elif mode == "--postflight":
        if not task_id or not loop_id:
            print(json.dumps({"aos_status": "fallback", "reason": "no task_id/loop_id"}, ensure_ascii=False))
            sys.exit(0)
        result = run_postflight(task_id, loop_id, session_id, cwd)

    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        sys.exit(2)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()