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
from aos.contract import (
    CONTRACT_VERSION,
    build_postflight,
    build_preflight,
    fallback_postflight,
    fallback_preflight,
)
from aos.core.evidence import collector as evidence_collector
from aos.core.loop import pending, stages
from aos.core.loop.state import LoopState
from aos.core.memory import inject
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


# A host-reported outcome maps onto the execution status the stages already
# understand. Anything unmapped stays "delegated", which finalize_stage treats
# as a half-closed loop rather than a completed one.
_DELEGATED_STATUS = {"success": "success", "failure": "failed", "partial": "partial"}


def _run_preflight(
    *,
    task: str,
    task_id: str = "",
    session_id: str = "",
    cwd: str = "",
    memory_mode: str = "enabled",
    provider: str = "host_delegate",
    model: str = "",
) -> tuple[LoopState, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    get_paths().ensure_store()
    if not session_id:
        # One session id for the whole loop, decided here and then persisted.
        # Every evidence path is keyed by it, so a loop whose session was
        # re-derived per call writes its before-snapshot into one directory and
        # reads it back from another — which is how a diff silently degrades into
        # "no baseline found". The host may name the session; then its name wins.
        session_id = evidence_collector.session_id()
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
    roles = stages.resolve_role_stage(state, decision)

    state.begin("recall")
    recall = stages.recall_stage(state, decision)

    state.begin("plan")
    plan = stages.plan_stage(state, recall=recall, roles=roles)
    stages.project_preflight_stage(state, project_root=cwd)
    stages.snapshot_before_stage(state, project_root=cwd)

    state.save()
    return state, decision, roles, recall, plan


def _memory_status(state: LoopState, recall: dict[str, Any]) -> str:
    """Recall health, as the host should read it: disabled, degraded, or fine."""
    if state.memory_mode in ("disabled", "off"):
        return "skipped"
    if recall.get("error"):
        return "degraded"
    return "ok"


def _preflight_doc(
    state: LoopState,
    decision: dict[str, Any],
    recall: dict[str, Any],
    *,
    schema_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    route = state.stage_data("route")
    lead_role = route.get("lead_role")
    support_roles = route.get("support_roles", [])
    warnings: list[str] = []
    status = "degraded" if (decision.get("fallback_reason") or not lead_role) else "ok"
    # A document that degrades must say why, in the field a host already reads.
    # `degraded` with an empty `warnings` is the shape that makes a human open the
    # database, which is the failure mode this loop was built to remove.
    if status == "degraded":
        if not lead_role:
            warnings.append("no concrete role resolved; routing degraded")
        if decision.get("fallback_reason"):
            warnings.append(f"routing fell back: {decision['fallback_reason']}")
    if recall.get("error"):
        warnings.append(f"recall failed; the host proceeded without memories: {recall['error']}")
    if state.memory_mode in ("disabled", "off"):
        warnings.append("memory disabled by request")
    # Rendered from the raw scored rows, which still carry title/body/tags;
    # _memory_view below is the trimmed contract view of the same recall.
    injection = inject.render(
        recall.get("memories", []),
        hypotheses=recall.get("hypotheses", []),
        route={
            "lead_skill": decision.get("selected", ""),
            "lead_role": lead_role,
            "confidence": decision.get("confidence", ""),
        },
    )
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
            "status": _memory_status(state, recall),
            "injection": injection,
        },
        skill={
            "lead_skill": decision.get("selected", ""),
            "support_skills": decision.get("support_skills", []),
        },
        warnings=warnings,
        artifacts={"loop_state": str(state.state_path())},
        schema_version=schema_version,
    )


def preflight(
    *,
    task: str,
    task_id: str = "",
    session_id: str = "",
    cwd: str = "",
    memory_mode: str = "enabled",
    provider: str = "host_delegate",
    model: str = "",
    schema_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    """Run the pre-execution stages and return the preflight contract."""
    try:
        state, decision, _roles, recall, _plan = _run_preflight(
            task=task,
            task_id=task_id,
            session_id=session_id,
            cwd=cwd,
            memory_mode=memory_mode,
            provider=provider,
            model=model,
        )
    except Exception as exc:  # fail-open: the host must still be able to proceed
        return fallback_preflight(
            f"preflight failed: {exc}",
            task_id=task_id,
            session_id=session_id,
            schema_version=schema_version,
        )
    doc = _preflight_doc(state, decision, recall, schema_version=schema_version)
    if doc["aos_status"] != "fallback" and doc["loop_id"]:
        # Written before the host starts working: if it never comes back, this file
        # is the only sign the run existed. A fail-open document records nothing —
        # there is no loop to close.
        injection = doc["memory"]["injection"]
        pending.record(
            session_id=doc["session_id"],
            loop_id=doc["loop_id"],
            task_id=doc["task_id"],
            cwd=cwd,
            task=task,
            injected_memories=[m["memory_id"] for m in injection["structured"]]
            if injection["structured"]
            else injection["memory_ids"],
            injection_chars=injection["char_count"],
        )
        # The pending record is deleted by the postflight, but the number is the
        # durable half of "the block the engine built is the block the host was
        # handed" — the plugin logs the length it appended, and without a persisted
        # counterpart there is nothing to compare it to after the run.
        state.record("recall", injection_chars=injection["char_count"], injected_memory_ids=injection["memory_ids"])
        state.save()
    return doc


def _validator_exit_codes(validation: dict[str, Any]) -> dict[str, Any]:
    """Pull the test/build exit codes the engine itself watched happen.

    ``validate_stage`` has already run the commands and knows the numbers; not
    forwarding them would make the engine throw away the strongest evidence it
    produced and then ask a human about a run it could have judged.
    """
    codes: dict[str, Any] = {}
    for key, field in (("test_exit_code", "test"), ("build_exit_code", "build")):
        result = validation.get(field) or {}
        status = str(result.get("status") or "")
        if status in ("", "SKIPPED", "NOT_AVAILABLE"):
            continue
        if "exit_code" in result:
            codes[key] = result.get("exit_code")
    return codes


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
    signals: Optional[dict[str, Any]] = None,
    store: Optional[MemoryStore] = None,
    schema_version: str = CONTRACT_VERSION,
) -> tuple[Optional[LoopState], dict[str, Any]]:
    state = LoopState.load(loop_id)
    if state is None:
        return None, fallback_postflight(
            "unknown loop_id", loop_id=loop_id, schema_version=schema_version
        )

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
            # The host ran the task, so its reported outcome is the only
            # verdict that exists. Reporting none must not read as a success —
            # that default is what made every delegated loop look like a win.
            execution = {
                "status": _DELEGATED_STATUS.get(outcome, "delegated"),
                "response_text": "",
                "delegated": True,
            }
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

        # One merged statement of what is known about this run: the host's
        # evidence, the engine's own observations, and any verdict either of them
        # declared. Everything after this point reads a verdict out of it, and
        # nothing invents one.
        received: dict[str, Any] = dict(signals or {})
        received.update(_validator_exit_codes(validation))
        if test_exit_code is not None:
            received.setdefault("test_exit_code", test_exit_code)
        if expected_files:
            received.setdefault("expected_files", expected_files)
        if outcome:
            received["outcome"] = outcome
        if quality_score is not None:
            received["quality_score"] = quality_score

        state.begin("record")
        record = stages.record_stage(
            state,
            execution=execution,
            plan=plan,
            signals=received,
            engine_evidence={
                "validation": validation,
                "files_changed": evidence["after"].get("files_changed", []),
            },
            store=store,
        )

        state.begin("evolve")
        learning = stages.evolve_stage(state, store=store)["summary"]

        state.begin("finalize")
        final = stages.finalize_stage(
            state,
            execution=execution,
            evidence=evidence,
            validation=validation,
            outcome=record["outcome"],
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
                "preexisting_files": evidence.get("preexisting_files", []),
                "test_passed": evidence["after"].get("test_passed"),
                "before_source": evidence.get("before_source", ""),
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
                "needs_review": bool(record.get("needs_review")),
            },
            replayed=False,
            schema_version=schema_version,
        )
        state.postflight = doc
        state.save()
        # The loop has reported back, so it no longer owes anything. Deleting the
        # record is what makes a *remaining* one meaningful.
        pending.clear(state.session_id)
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
    signals: Optional[dict[str, Any]] = None,
    schema_version: str = CONTRACT_VERSION,
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
            signals=signals,
            schema_version=schema_version,
        )
    except Exception as exc:  # fail-open: never break the host on finalisation
        return fallback_postflight(
            f"postflight failed: {exc}",
            task_id=task_id,
            loop_id=loop_id,
            session_id=session_id,
            schema_version=schema_version,
        )
    return doc


def run(
    *,
    task: str,
    cwd: str = "",
    provider: str = "host_delegate",
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
        state, decision, _roles, recall, _plan = _run_preflight(
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
