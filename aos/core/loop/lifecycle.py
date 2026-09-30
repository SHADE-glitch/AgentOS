"""Loop lifecycle: preflight, postflight and the full run.

One state machine serves both callers:

  * the CLI / an in-process agent calls :func:`run` (preflight -> execute ->
    postflight);
  * a host that owns execution calls :func:`preflight`, then :func:`postflight`
    when it is done — the same record/evolve stages run, so the learning loop
    closes for host-delegated tasks too.

Stage order is ``route -> resolve_role -> recall -> plan -> execute ->
evidence -> record -> evolve -> finalize``. Recall runs after routing (rather
than before, as the old pipeline listed it) because the retrieval query is
derived from the routing classification.
"""

from __future__ import annotations

from typing import Any, Optional

from aos.adapters import base as adapters_base
from aos.config import get_paths
from aos.contract import build_postflight, build_preflight, fallback_postflight, fallback_preflight
from aos.core.loop import stages
from aos.core.loop.state import LoopState
from aos.core.memory.store import MemoryStore


def _memory_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": row.get("memory_id", ""),
        "type": row.get("type", ""),
        "content": row.get("content") or row.get("body") or row.get("title", ""),
        "score": row.get("final_score", 0.0),
        "evidence_level": row.get("evidence_level", ""),
        "confidence": row.get("confidence", ""),
    }


def _run_preflight(
    *,
    task: str,
    task_id: str = "",
    session_id: str = "",
    cwd: str = "",
    memory_mode: str = "enabled",
    provider: str = "opencode",
    model: str = "",
) -> tuple[LoopState, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    get_paths().ensure_store()
    state = LoopState.new(
        task_text=task,
        cwd=cwd,
        session_id=session_id,
        memory_mode=memory_mode,
        provider=provider,
        model=model,
        task_id=task_id,
    )
    state.save()

    state.begin("route")
    decision = stages.route_stage(state)

    state.begin("resolve_role")
    executor = stages.resolve_role_stage(state, decision)

    state.begin("recall")
    recall = stages.recall_stage(state, decision)

    state.begin("plan")
    plan = stages.plan_stage(state, recall=recall, executor=executor)
    stages.project_preflight_stage(state, project_root=cwd)

    state.save()
    return state, decision, executor, recall, plan


def _preflight_doc(state: LoopState, decision: dict[str, Any], recall: dict[str, Any]) -> dict[str, Any]:
    route = state.stage_data("route")
    lead_role = route.get("lead_role")
    support_roles = route.get("support_roles", [])
    warnings: list[str] = []
    if not lead_role:
        warnings.append("no concrete role resolved; routing degraded")
    if state.memory_mode in ("disabled", "off"):
        warnings.append("memory disabled by request")

    status = "degraded" if (decision.get("fallback_reason") or not lead_role) else "ok"
    return build_preflight(
        task_id=state.task_id,
        loop_id=state.loop_id,
        session_id=state.session_id,
        aos_status=status,
        classification={
            "category": decision.get("primary_domain", ""),
            "domains": decision.get("domains", []),
            "roles": [r for r in ([lead_role] + list(support_roles)) if r],
            "keywords": (recall.get("query") or {}).get("keywords", []),
            "difficulty": state.stage_data("route").get("artifact", {}).get("difficulty", "medium"),
        },
        router={
            "intent": decision.get("intent", ""),
            "taxonomy": "abstract",
            "lead_skill": decision.get("selected", ""),
            "lead_role": lead_role,
            "support_skills": decision.get("support_skills", []),
            "support_roles": support_roles,
            "confidence": decision.get("confidence", "low"),
            "confidence_numeric": decision.get("confidence_numeric", 0.0),
            "route_mode": decision.get("route_mode", "lexical"),
            "escalation_reason": decision.get("escalation_reason"),
            "fallback_reason": decision.get("fallback_reason"),
            "artifact": decision,
        },
        memory={
            "retrieved": recall.get("retrieved", 0),
            "memories": [_memory_view(m) for m in recall.get("memories", [])],
            "hypotheses": [_memory_view(h) for h in recall.get("hypotheses", [])],
            "ranking": recall.get("ranking", []),
        },
        skill={
            "lead_skill": decision.get("selected", ""),
            "support_skills": decision.get("support_skills", []),
            "skills_loaded": [],
        },
        warnings=warnings,
        artifacts={"loop_state": str(state.state_path())},
    )


def preflight(
    *,
    task: str,
    task_id: str = "",
    session_id: str = "",
    cwd: str = "",
    memory_mode: str = "enabled",
    provider: str = "opencode",
    model: str = "",
) -> dict[str, Any]:
    """Run the pre-execution stages and return the preflight contract."""
    try:
        state, decision, _executor, recall, _plan = _run_preflight(
            task=task,
            task_id=task_id,
            session_id=session_id,
            cwd=cwd,
            memory_mode=memory_mode,
            provider=provider,
            model=model,
        )
    except Exception as exc:  # fail-open: the host must still be able to proceed
        return fallback_preflight(f"preflight failed: {exc}", task_id=task_id, session_id=session_id)
    return _preflight_doc(state, decision, recall)


def _run_postflight(
    *,
    loop_id: str,
    project_root: str = "",
    test_command: str = "",
    test_stdout: str = "",
    test_stderr: str = "",
    test_exit_code: Optional[int] = None,
    compile_command: str = "",
    expected_files: Optional[list[str]] = None,
    validate: bool = True,
    execution: Optional[dict[str, Any]] = None,
    outcome: str = "",
    quality_score: Optional[float] = None,
    store: Optional[MemoryStore] = None,
) -> tuple[Optional[LoopState], dict[str, Any]]:
    state = LoopState.load(loop_id)
    if state is None:
        return None, fallback_postflight("unknown loop_id", loop_id=loop_id)

    # Idempotency: a finished loop returns its stored document, flagged.
    if state.postflight is not None and state.final_status != "pending":
        doc = dict(state.postflight)
        doc["replayed"] = True
        return state, doc

    owns_store = store is None
    store = store or MemoryStore()
    try:
        execution = execution if execution is not None else dict(state.stage_data("execute"))
        if not execution:
            execution = {"status": "success", "response_text": "", "delegated": False}
        plan = state.stage_data("plan")

        state.begin("evidence")
        evidence = stages.evidence_stage(
            state,
            project_root=project_root or state.cwd,
            test_command=test_command,
            test_stdout=test_stdout,
            test_stderr=test_stderr,
            test_exit_code=test_exit_code,
        )

        state.begin("validate")
        validation = stages.validate_stage(
            state,
            project_root=project_root or state.cwd,
            compile_command=compile_command,
            test_command=test_command,
            expected_files=expected_files,
            enabled=validate,
        )

        state.begin("record")
        record = stages.record_stage(
            state,
            execution=execution,
            plan=plan,
            test_exit_code=test_exit_code,
            outcome=outcome,
            quality_score=quality_score,
            store=store,
        )

        state.begin("evolve")
        learning = stages.evolve_stage(state, store=store)["summary"]

        state.begin("finalize")
        final = stages.finalize_stage(
            state, execution=execution, evidence=evidence, validation=validation
        )

        doc = build_postflight(
            task_id=state.task_id,
            loop_id=state.loop_id,
            session_id=state.session_id,
            aos_status="degraded" if final["failures"] else "ok",
            final_status=state.final_status,
            evidence_path=evidence["path"],
            evidence={
                "path": evidence["path"],
                "repo_resolved": evidence["after"].get("repo_resolved", False),
                "files_changed": evidence["after"].get("files_changed", []),
                "test_passed": evidence["after"].get("test_passed"),
            },
            recovery={
                "failures_detected": len(final["failures"]),
                "recovery_attempted": final["recovery_attempted"],
                "recovery_success": final["recovery_success"],
                "final_status": final["final_status"],
                "plan": final["plan"],
            },
            learning={
                "candidates_recorded": record.get("candidates_created", 0),
                "hypotheses_pending_review": learning.get("pending_reviews", 0),
                "promoted": learning.get("promoted", 0),
            },
            replayed=False,
        )
        state.postflight = doc
        state.save()
        return state, doc
    finally:
        if owns_store:
            store.close()


def postflight(
    *,
    task_id: str = "",
    loop_id: str = "",
    session_id: str = "",
    cwd: str = "",
    test_command: str = "",
    test_stdout: str = "",
    test_stderr: str = "",
    test_exit_code: Optional[int] = None,
    compile_command: str = "",
    expected_files: Optional[list[str]] = None,
    validate: bool = True,
    execution: Optional[dict[str, Any]] = None,
    outcome: str = "",
    quality_score: Optional[float] = None,
) -> dict[str, Any]:
    """Run the post-execution stages and return the postflight contract."""
    try:
        _state, doc = _run_postflight(
            loop_id=loop_id,
            project_root=cwd,
            test_command=test_command,
            test_stdout=test_stdout,
            test_stderr=test_stderr,
            test_exit_code=test_exit_code,
            compile_command=compile_command,
            expected_files=expected_files,
            validate=validate,
            execution=execution,
            outcome=outcome,
            quality_score=quality_score,
        )
    except Exception as exc:  # fail-open: never break the host on finalisation
        return fallback_postflight(
            f"postflight failed: {exc}", task_id=task_id, loop_id=loop_id, session_id=session_id
        )
    return doc


def run(
    *,
    task: str,
    cwd: str = "",
    provider: str = "opencode",
    model: str = "",
    memory_mode: str = "enabled",
    session_id: str = "",
    task_id: str = "",
    test_command: str = "",
    test_exit_code: Optional[int] = None,
    test_stdout: str = "",
    test_stderr: str = "",
    compile_command: str = "",
    expected_files: Optional[list[str]] = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Full loop: preflight, execute through the provider, then postflight."""
    try:
        state, decision, _executor, recall, _plan = _run_preflight(
            task=task,
            task_id=task_id,
            session_id=session_id,
            cwd=cwd,
            memory_mode=memory_mode,
            provider=provider,
            model=model,
        )
    except Exception as exc:
        return fallback_postflight(f"preflight failed: {exc}", task_id=task_id)

    prompt = stages.build_prompt(state, decision=decision, recall=recall)
    state.begin("execute")
    try:
        provider_obj = adapters_base.get(provider)
        execution = stages.execute_stage(state, provider_obj, prompt=prompt, cwd=cwd)
    except Exception as exc:
        state.fail("execute", exc, critical=False)
        execution = {"status": "error", "error": str(exc), "response_text": "", "delegated": False}
    state.save()

    _state, doc = _run_postflight(
        loop_id=state.loop_id,
        project_root=cwd,
        test_command=test_command,
        test_stdout=test_stdout,
        test_stderr=test_stderr,
        test_exit_code=test_exit_code,
        compile_command=compile_command,
        expected_files=expected_files,
        validate=validate,
        execution=execution,
    )
    return doc
