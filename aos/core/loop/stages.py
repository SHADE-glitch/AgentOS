"""The individual loop stages.

Each function takes the :class:`LoopState`, does one job, records its result
on the state, and returns that result. The lifecycle wires them together; the
CLI and the host postflight both drive the same functions, which is what makes
the learning loop close for host-delegated runs too.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from aos.core.evidence import collector as evidence_collector
from aos.core.evidence import recovery
from aos.core.loop.state import LoopState
from aos.core.loop.team import plan_executor
from aos.core.memory import evolve as evolve_mod
from aos.core.memory import evaluate as evaluate_mod
from aos.core.memory.record import record_outcome
from aos.core.memory.retrieve import retrieve
from aos.core.memory.store import MemoryStore
from aos.core.validation import project_preflight
from aos.core.validation.code_validator import validate_code_changes

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "into", "then", "than",
        "when", "what", "your", "you", "are", "was", "were", "will", "would", "should",
        "can", "could", "have", "has", "had", "not", "but", "all", "any", "how", "why",
        "use", "using", "fix", "add", "make", "please", "need", "want", "help",
    }
)


# ── route ──────────────────────────────────────────────────────────────
def route_stage(state: LoopState, *, store: Optional[MemoryStore] = None) -> dict[str, Any]:
    """Classify the task and pick a lead skill + concrete role."""
    from aos.core.routing.router import route_task

    decision = route_task(state.task_text)
    state.complete(
        "route",
        intent=decision.get("intent", ""),
        lead_skill=decision.get("selected", ""),
        lead_role=decision.get("lead_role"),
        support_skills=decision.get("support_skills", []),
        support_roles=decision.get("support_roles", []),
        confidence=decision.get("confidence", "low"),
        confidence_numeric=decision.get("confidence_numeric", 0.0),
        route_mode=decision.get("route_mode", "lexical"),
        escalation_reason=decision.get("escalation_reason"),
        fallback_reason=decision.get("fallback_reason"),
        domains=decision.get("domains", []),
        artifact=decision,
    )
    return decision


def resolve_role_stage(state: LoopState, decision: dict[str, Any]) -> dict[str, Any]:
    """Resolve the concrete role(s) and form a team if the task warrants one."""
    lead_role = decision.get("lead_role")
    support_roles = decision.get("support_roles", [])
    executor = plan_executor(
        task=state.task_text,
        lead_role=lead_role or "",
        support_roles=support_roles,
        domains=decision.get("domains", []),
        difficulty=decision.get("difficulty", "medium"),
        intent=decision.get("intent", ""),
    )
    state.complete(
        "resolve_role",
        lead_role=executor.lead_role,
        support_roles=executor.support_roles,
        executor=executor.to_dict(),
    )
    return {
        "lead_role": executor.lead_role,
        "support_roles": executor.support_roles,
        "executor": executor.to_dict(),
    }


# ── recall ─────────────────────────────────────────────────────────────
def _keywords(task_text: str, decision: dict[str, Any]) -> list[str]:
    words = re.findall(r"[a-z0-9_\-]{3,}", task_text.lower())
    keywords = [w for w in words if w not in _STOPWORDS]
    for extra in (decision.get("selected", ""), *decision.get("domains", [])):
        if extra and extra != "fallback":
            keywords.append(str(extra))
    seen: list[str] = []
    for word in keywords:
        if word not in seen:
            seen.append(word)
    return seen[:8]


def recall_stage(
    state: LoopState, decision: dict[str, Any], *, store: Optional[MemoryStore] = None
) -> dict[str, Any]:
    """Retrieve relevant memories. Never fatal: on error the loop continues."""
    if state.memory_mode in ("disabled", "off"):
        state.complete("recall", retrieved=0, memory_ids=[], hypotheses=[], skipped=True)
        return {"memories": [], "hypotheses": [], "ranking": [], "retrieved": 0}

    query = {
        "task_text": state.task_text,
        "category": decision.get("primary_domain", "") or "",
        "domains": decision.get("domains", []),
        "roles": [r for r in ([decision.get("lead_role")] + decision.get("support_roles", [])) if r],
        "keywords": _keywords(state.task_text, decision),
        "difficulty": "medium",
        "exclude_hypothesis": False,
    }
    result = retrieve(query, store=store, loop_id=state.loop_id)
    memories, hypotheses = [], []
    for row in result.get("results", []):
        (hypotheses if row.get("is_hypothesis") else memories).append(row)
    state.complete(
        "recall",
        retrieved=len(memories) + len(hypotheses),
        memory_ids=[m["memory_id"] for m in memories],
        hypotheses=[h["memory_id"] for h in hypotheses],
        ranking=[r["memory_id"] for r in result.get("results", [])],
        query=query,
    )
    return {
        "memories": memories,
        "hypotheses": hypotheses,
        "ranking": [r["memory_id"] for r in result.get("results", [])],
        "retrieved": len(memories) + len(hypotheses),
        "query": query,
    }


# ── plan ───────────────────────────────────────────────────────────────
def plan_stage(state: LoopState, *, recall: dict[str, Any], executor: dict[str, Any]) -> dict[str, Any]:
    """Assemble the context to inject into execution."""
    memories = recall.get("memories", [])
    plan = {
        "lead_role": executor.get("lead_role"),
        "support_roles": executor.get("support_roles", []),
        "memory_ids": [m["memory_id"] for m in memories],
        "hypothesis_ids": [h["memory_id"] for h in recall.get("hypotheses", [])],
        "multi_agent": executor.get("is_multi_agent", False),
        "team_id": executor.get("team_id", ""),
        "task_cards": executor.get("task_cards", []),
    }
    state.complete("plan", **plan)
    return plan


def build_prompt(state: LoopState, *, decision: dict[str, Any], recall: dict[str, Any]) -> str:
    """Build the prompt handed to the provider, including the injected context."""
    lines: list[str] = []
    lead_role = decision.get("lead_role") or decision.get("selected") or "engineer"
    lines.append(f"Act as a {lead_role}.")
    support = [r for r in decision.get("support_roles", []) if r]
    if support:
        lines.append(f"Support roles available: {', '.join(support)}.")
    lines.append("")
    lines.append("Task:")
    lines.append(state.task_text)
    memories = recall.get("memories", [])
    if memories:
        lines.append("")
        lines.append("Relevant memory (apply where it fits):")
        for memory in memories:
            body = (memory.get("content") or memory.get("body") or "").strip()
            lines.append(f"- [{memory['memory_id']}] {body[:400]}")
    hypotheses = recall.get("hypotheses", [])
    if hypotheses:
        lines.append("")
        lines.append("Unverified hypotheses (treat as hints, not facts):")
        for hypothesis in hypotheses:
            lines.append(f"- [{hypothesis['memory_id']}] {hypothesis.get('content', '')[:300]}")
    return "\n".join(lines)


# ── execute ────────────────────────────────────────────────────────────
def execute_stage(state: LoopState, provider: Any, *, prompt: str, cwd: str = "") -> dict[str, Any]:
    """Run the task through the provider and record the normalised result."""
    result = provider.invoke(prompt=prompt, model=state.model, cwd=cwd or state.cwd)
    payload = result.to_dict()
    if result.ok:
        state.complete("execute", **payload)
    elif result.delegated:
        state.complete("execute", **payload)
    else:
        state.fail("execute", result.error or result.status, critical=False)
        state.complete("execute", **payload)
    return payload


# ── evidence ───────────────────────────────────────────────────────────
def evidence_stage(
    state: LoopState,
    *,
    project_root: str = "",
    before: Optional[dict[str, Any]] = None,
    test_command: str = "",
    test_stdout: str = "",
    test_stderr: str = "",
    test_exit_code: Optional[int] = None,
) -> dict[str, Any]:
    """Collect and persist git/test evidence for the task."""
    root = project_root or state.cwd
    before = before or evidence_collector.collect_before(
        state.task_id, project_root=root, loop_id=state.loop_id, session=state.session_id
    )
    after = evidence_collector.collect_after(
        state.task_id,
        before,
        project_root=root,
        loop_id=state.loop_id,
        test_command=test_command,
        test_stdout=test_stdout,
        test_stderr=test_stderr,
        test_exit_code=test_exit_code,
        session=state.session_id,
    )
    path = evidence_collector.save_evidence(state.task_id, before, after, session=state.session_id)
    state.complete(
        "evidence",
        path=str(path),
        repo_resolved=after.get("repo_resolved", False),
        files_changed=after.get("files_changed", []),
        test_passed=after.get("test_passed"),
    )
    return {"before": before, "after": after, "path": str(path)}


# ── project preflight ──────────────────────────────────────────────────
def project_preflight_stage(state: LoopState, *, project_root: str = "") -> dict[str, Any]:
    """Detect the project's build system, runtime and validation commands."""
    root = project_root or state.cwd or "."
    result = project_preflight.run_preflight(root).to_dict()
    state.complete(
        "plan",
        project_preflight={
            "project_root": result["project_root"],
            "status": result["status"],
            "build_system": result["build_system"],
            "build_file": result["build_file"],
            "compile_command": result["compile_command"],
            "test_command": result["test_command"],
            "environment_blockers": result["environment_blockers"],
        },
    )
    return result


# ── validate ───────────────────────────────────────────────────────────
def validate_stage(
    state: LoopState,
    *,
    project_root: str = "",
    compile_command: str = "",
    test_command: str = "",
    expected_files: Optional[list[str]] = None,
    baseline: Optional[dict[str, Any]] = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Run post-execution code validation, unless there is nothing to run.

    The *compile* command is taken from the caller or, failing that, from the
    detected build system. A project's test suite is only run when the caller
    explicitly supplies ``test_command`` — silently executing an unknown
    project's full test suite is expensive and can have side effects.
    """
    root = project_root or state.cwd or "."
    preflight = state.stage_data("plan").get("project_preflight") or {}
    compile_command = compile_command or preflight.get("compile_command", "")

    if not enabled:
        state.complete("validate", validation_status="SKIPPED", reason="disabled by request")
        return {"validation_status": "SKIPPED", "reason": "disabled by request"}

    if not compile_command and not test_command:
        reason = "no compile or test command available"
        state.complete("validate", validation_status="SKIPPED", reason=reason)
        return {"validation_status": "SKIPPED", "reason": reason}

    result = validate_code_changes(
        project_root=root,
        execution_id=state.loop_id,
        expected_files=expected_files,
        compile_command=compile_command,
        test_command=test_command,
        baseline=baseline,
    )
    state.complete(
        "validate",
        validation_status=result.validation_status,
        files_changed=[c.path for c in result.files_changed],
        unexpected_files=result.unexpected_files_changed,
        build_status=result.build.status,
        test_status=result.test.status,
    )
    return result.to_dict()


# ── record ─────────────────────────────────────────────────────────────
def _outcome_for(execution: dict[str, Any], test_exit_code: Optional[int]) -> str:
    status = execution.get("status", "")
    if status in ("error", "timeout", "failed"):
        return "failure"
    if test_exit_code is not None and test_exit_code != 0:
        return "failure"
    if status == "success":
        return "success"
    return "partial"


def record_stage(
    state: LoopState,
    *,
    execution: dict[str, Any],
    plan: dict[str, Any],
    test_exit_code: Optional[int] = None,
    outcome: str = "",
    quality_score: Optional[float] = None,
    store: Optional[MemoryStore] = None,
) -> dict[str, Any]:
    """Write observations and candidate changes for the finished loop.

    ``outcome`` and ``quality_score`` may be supplied by a host that knows
    them better than the engine can infer (e.g. a delegated run).
    """
    response_text = execution.get("response_text", "") or ""
    quality = (
        float(quality_score)
        if quality_score is not None
        else evaluate_mod.compute_quality_score(response_text)
    )
    resolved_outcome = outcome or _outcome_for(execution, test_exit_code)
    source_hash = hashlib.sha1(response_text.encode("utf-8")).hexdigest()[:16] if response_text else ""

    counts = record_outcome(
        loop_id=state.loop_id,
        outcome=resolved_outcome,
        quality_score=quality,
        task_id=state.task_id,
        session_id=state.session_id,
        source_hash=source_hash,
        memories_used=plan.get("memory_ids", []),
        store=store,
    )
    state.complete(
        "record",
        outcome=resolved_outcome,
        quality_score=quality,
        observations=counts["observations_recorded"],
        candidates=counts["candidates_created"],
    )
    return {
        "outcome": resolved_outcome,
        "quality_score": quality,
        "source_hash": source_hash,
        **counts,
    }


# ── evolve ─────────────────────────────────────────────────────────────
def evolve_stage(state: LoopState, *, store: Optional[MemoryStore] = None) -> dict[str, Any]:
    """Run the learning pipeline (validate -> gate -> promote/review)."""
    report = evolve_mod.run_learning(store=store)
    summary = report["summary"]
    state.complete(
        "evolve",
        promoted=summary["promoted"],
        reviews_created=summary["reviews_created"],
        rejected=summary["rejected"],
        pending_reviews=summary["pending_reviews"],
        evaluations=summary["evaluations"],
    )
    return report


# ── finalize ───────────────────────────────────────────────────────────
def finalize_stage(
    state: LoopState,
    *,
    execution: dict[str, Any],
    evidence: dict[str, Any],
    validation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Detect failures, plan recovery (never execute it) and set the status."""
    failures = recovery.detect_failures(
        task_id=state.task_id,
        loop_id=state.loop_id,
        execution=execution,
        evidence=evidence,
    )
    plan = recovery.plan_recovery(failures, task_id=state.task_id, loop_id=state.loop_id)

    if state.final_status != "failed":
        status = execution.get("status", "")
        after = evidence.get("after", {}) if evidence else {}
        test_passed = after.get("test_passed")
        validation_status = (validation or {}).get("validation_status", "SKIPPED")
        if status in ("error", "timeout", "failed"):
            state.final_status = "failed"
        elif validation_status == "FAIL":
            state.final_status = "partial"
        elif status == "delegated":
            # The host owns execution; the loop is only half closed.
            state.final_status = "partial"
        elif test_passed is False:
            state.final_status = "partial"
        else:
            state.final_status = "completed"

    state.complete(
        "finalize",
        final_status=state.final_status,
        failures_detected=len(failures),
        recovery_needed=plan["recovery_needed"],
        validation_status=(validation or {}).get("validation_status", "SKIPPED"),
    )
    return {
        "failures": failures,
        "plan": plan,
        "final_status": state.final_status,
        "recovery_attempted": False,
        "recovery_success": False,
    }
