"""The individual loop stages.

Each function takes the :class:`LoopState`, does one job, records its result
on the state, and returns that result. The lifecycle wires them together; the
CLI and the host postflight both drive the same functions, which is what makes
the learning loop close for host-delegated runs too.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Optional

from aos.core import outcome as outcome_mod
from aos.core.evidence import collector as evidence_collector
from aos.core.evidence import recovery
from aos.core.loop.state import LoopState
from aos.core.memory import evolve as evolve_mod
from aos.core.memory import inject
from aos.core.memory import record as record_mod
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
    """Resolve the concrete role(s) the routed skills map to."""
    lead_role = decision.get("lead_role") or ""
    support_roles = [r for r in (decision.get("support_roles") or []) if r]
    state.complete("resolve_role", lead_role=lead_role, support_roles=support_roles)
    return {"lead_role": lead_role, "support_roles": support_roles}


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
    """Retrieve relevant memories. Never fatal — but a failure is written down.

    "Never fatal" used to be a docstring with no try/except behind it, so a store
    that raised took the whole preflight into the fail-open path and the recorded
    reason was a generic preflight failure rather than "recall broke". The host
    still gets to proceed; the loop says what actually happened.
    """
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
        # Scope travels with the query. Without it a memory learned in one
        # repository is offered as fact in another, and the `scope` column —
        # which the gate already writes — stays a label nobody filters on.
        "scope_project": Path(state.cwd).name if state.cwd else "",
        "scope_session": state.session_id or "",
    }
    try:
        result = retrieve(query, store=store, loop_id=state.loop_id)
    except Exception as exc:
        state.fail("recall", exc, critical=False)
        state.record(
            "recall",
            retrieved=0,
            memory_ids=[],
            hypotheses=[],
            ranking=[],
            query=query,
            error=str(exc),
        )
        return {
            "memories": [],
            "hypotheses": [],
            "ranking": [],
            "retrieved": 0,
            "query": query,
            "error": f"recall failed: {exc}",
        }
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
def plan_stage(state: LoopState, *, recall: dict[str, Any], roles: dict[str, Any]) -> dict[str, Any]:
    """Assemble the context to inject into execution."""
    memories = recall.get("memories", [])
    plan = {
        "lead_role": roles.get("lead_role"),
        "support_roles": roles.get("support_roles", []),
        "memory_ids": [m["memory_id"] for m in memories],
        "hypothesis_ids": [h["memory_id"] for h in recall.get("hypotheses", [])],
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
    injection = inject.render(
        recall.get("memories", []),
        hypotheses=recall.get("hypotheses", []),
        route={
            "lead_skill": decision.get("selected", ""),
            "lead_role": decision.get("lead_role", ""),
            "confidence": decision.get("confidence", ""),
        },
    )
    if injection["text"]:
        lines.extend(["", injection["text"]])
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
        # Fail, and stay failed. The old sequence called complete() on the same
        # entry immediately after, which rewrote the status back to "completed"
        # and erased the only record that the run had failed — the loop then
        # looked healthy while the payload said otherwise.
        state.fail("execute", result.error or result.status, critical=False)
        state.record("execute", **payload)
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
    source = "caller"
    if before is None:
        before = evidence_collector.read_before(state.task_id, session=state.session_id)
        source = "preflight" if before else "recaptured at postflight"
    if before is None:
        before = evidence_collector.collect_before(
            state.task_id, project_root=root, loop_id=state.loop_id, session=state.session_id
        )
        source = "recaptured at postflight"
    preexisting = (before.get("git_status") or "").strip() if source == "preflight" else ""
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
    # Files that were already dirty before the run are not this run's work, and a
    # reviewer comparing `files_changed` against the diff needs to know which is
    # which rather than discovering it by reading git status themselves.
    changed = after.get("files_changed", [])
    # `git status --porcelain` puts the path last (` M src/a.py`, `?? new.py`).
    already = {line.split()[-1] for line in preexisting.splitlines() if line.strip()}
    preexisted = [f for f in changed if f in already]
    state.complete(
        "evidence",
        path=str(path),
        repo_resolved=after.get("repo_resolved", False),
        files_changed=changed,
        preexisting_files=preexisted,
        test_passed=after.get("test_passed"),
        before_source=source,
    )
    return {
        "before": before,
        "after": after,
        "path": str(path),
        "before_source": source,
        "preexisting_files": preexisted,
    }


# ── pre-execution evidence ─────────────────────────────────────────────
def snapshot_before_stage(state: LoopState, *, project_root: str = "") -> dict[str, Any]:
    """Take the pre-execution snapshot while the tree is still the tree it started with.

    Collecting this in postflight — which is where it used to happen — diffs a
    dirty working tree against itself, so `files_changed` reported whatever the
    developer had uncommitted before the task began, not what the task did. The
    snapshot also has to survive the host dying between the two calls, so it goes
    to disk immediately.
    """
    root = project_root or state.cwd
    before = evidence_collector.collect_before(
        state.task_id, project_root=root, loop_id=state.loop_id, session=state.session_id
    )
    if root:
        evidence_collector.write_before(before, session=state.session_id)
    state.record(
        "evidence",
        before=before,
        before_at=before.get("timestamp", ""),
        repo_resolved=before.get("repo_resolved", False),
        working_tree_dirty=before.get("working_tree_dirty", False),
    )
    return before


# ── project preflight ──────────────────────────────────────────────────
def project_preflight_stage(state: LoopState, *, project_root: str = "") -> dict[str, Any]:
    """Detect the project's build system, runtime and validation commands.

    No fallback to the process's own directory: a host that omits ``cwd`` would
    otherwise have the engine inspect — and later run commands in — whatever
    directory the CLI happened to be started in. The project is what the caller
    names, or there is no project.
    """
    root = project_root or state.cwd
    if not root:
        result = {
            "project_root": "",
            "status": "skipped",
            "build_system": "",
            "build_file": "",
            "compile_command": "",
            "test_command": "",
            "environment_blockers": [],
            "reason": "no project root reported",
        }
    else:
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
    root = project_root or state.cwd
    preflight = state.stage_data("plan").get("project_preflight") or {}
    compile_command = compile_command or preflight.get("compile_command", "")

    if not enabled:
        state.complete("validate", validation_status="SKIPPED", reason="disabled by request")
        return {"validation_status": "SKIPPED", "reason": "disabled by request"}

    if not root:
        # Running a detected build command in a directory nobody named is worse
        # than not validating: it produces a verdict the host never asked for, in
        # someone else's project, and the loop then learns from it.
        state.complete("validate", validation_status="SKIPPED", reason="no project root reported")
        return {"validation_status": "SKIPPED", "reason": "no project root reported"}

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
def record_stage(
    state: LoopState,
    *,
    execution: dict[str, Any],
    plan: dict[str, Any],
    signals: Optional[dict[str, Any]] = None,
    engine_evidence: Optional[dict[str, Any]] = None,
    store: Optional[MemoryStore] = None,
    propose: bool = True,
) -> dict[str, Any]:
    """Synthesise the loop's verdict, then write observations and candidates.

    ``signals`` is everything the host reported *and* everything the engine
    observed, already merged by the caller: the point of the merge is that
    :func:`aos.core.outcome.synthesize` is then the only place a verdict is
    decided. Nothing here guesses at success any more — a run nobody described is
    recorded as a run nobody described, and asks.
    """
    received = dict(signals or {})

    # An engine-owned run reports through `execution`; translate it into the same
    # vocabulary a host uses so there is one decision path, not two.
    status = str(execution.get("status") or "")
    if status in ("error", "timeout", "failed") and not received.get("session_error"):
        received["session_error"] = execution.get("error") or status
    response_text = execution.get("response_text", "") or ""
    if response_text and not received.get("response_summary"):
        received["response_summary"] = response_text

    evidence = engine_evidence or {}
    # Everything that reached the prompt is in play — the ranked memories *and*
    # the hypothesis-lane hints. A hint was in front of the model too, so a run
    # that failed while following it is evidence against it, and excluding hints
    # here would leave the only evidence a gate can act on unreachable.
    memories_used = list(
        dict.fromkeys(
            [m for m in (plan.get("memory_ids") or []) if m]
            + [h for h in (plan.get("hypothesis_ids") or []) if h]
        )
    )
    route = state.stage_data("route") or {}
    artifact = route.get("artifact") or {}
    category = str(artifact.get("primary_domain") or route.get("lead_skill") or "")
    skills = [s for s in ([route.get("lead_skill")] + list(route.get("support_skills") or [])) if s]
    received["files_changed"] = evidence.get("files_changed") or []

    synthesis = outcome_mod.synthesize(received, engine_evidence=evidence)
    # The hash identifies the run, not its prose. Deriving it from response_text
    # alone meant a delegated run — which has no response text in the engine, and
    # is exactly what opencode produces — never had execution evidence, so every
    # proposal it made was rejected as fabricated.
    source_hash = hashlib.sha1(
        f"{state.loop_id}\n{synthesis['outcome']}\n{response_text}".encode("utf-8")
    ).hexdigest()[:16]

    proposal = None
    if propose and record_mod.should_propose(
        outcome=synthesis["outcome"],
        memories_used=memories_used,
        needs_review=synthesis["needs_review"],
    ):
        proposal = record_mod.proposal_for_loop(
            loop_id=state.loop_id,
            task_text=state.task_text,
            outcome=synthesis["outcome"],
            cwd=state.cwd,
            category=category,
            skills=skills,
            files_changed=evidence.get("files_changed"),
            quality_score=synthesis["quality_score"],
        )

    # The stored snapshot is what a reviewer reads and what a later label is
    # applied to, so it carries the run's identity, not only its numbers: after
    # the loop state file is gone this is the only record of what was asked.
    snapshot = {
        **synthesis["signals"],
        "present": synthesis["present"],
        "absent": synthesis["absent"],
        "mass": synthesis["mass"],
        "score": synthesis["score"],
        "reasons": synthesis["reasons"],
        "task": state.task_text[:200],
        "cwd": state.cwd,
        "category": category,
        "skills": skills,
        "memories_used": memories_used,
    }
    counts = record_mod.record_outcome(
        loop_id=state.loop_id,
        outcome=synthesis["outcome"],
        quality_score=synthesis["quality_score"],
        task_id=state.task_id,
        session_id=state.session_id,
        source_hash=source_hash,
        memories_used=memories_used,
        store=store,
        confidence=synthesis["confidence"],
        signals=snapshot,
        needs_review=synthesis["needs_review"],
        synthesised=synthesis["synthesised"],
        # The host's report, not the engine's own routing label. Attribution has
        # to come from outside the loop that chose the memory, or "it was routed
        # to this skill" becomes "this memory earned its keep" — the same
        # circular credit the recall counters used to hand out.
        skill_used=str((signals or {}).get("skill_used") or ""),
        proposal=proposal,
    )
    state.complete(
        "record",
        outcome=synthesis["outcome"],
        quality_score=synthesis["quality_score"],
        confidence=synthesis["confidence"],
        mass=synthesis["mass"],
        needs_review=synthesis["needs_review"],
        synthesised=synthesis["synthesised"],
        explicit=synthesis["explicit"],
        observations=counts["observations_recorded"],
        candidates=counts["candidates_created"],
        proposals=counts["proposals_created"],
        memories_used=[m for m in (plan.get("memory_ids") or []) if m],
        reason=synthesis["reasons"][0] if synthesis["reasons"] else "",
    )
    return {"outcome": synthesis["outcome"], "quality_score": synthesis["quality_score"],
            "confidence": synthesis["confidence"], "needs_review": synthesis["needs_review"],
            "source_hash": source_hash, **counts}


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
# The loop's completion state is the recorded verdict seen from the other side:
# keeping a second, independent calculation of it is how one half of the engine
# reported "completed" while the other half had no idea what had happened.
_FINAL_BY_OUTCOME = {"success": "completed", "partial": "partial", "failure": "failed"}


def finalize_stage(
    state: LoopState,
    *,
    execution: dict[str, Any],
    evidence: dict[str, Any],
    validation: Optional[dict[str, Any]] = None,
    outcome: str = "",
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
        state.final_status = _FINAL_BY_OUTCOME.get(outcome, "partial")

    state.complete(
        "finalize",
        final_status=state.final_status,
        failures_detected=len(failures),
        recovery_needed=plan["recovery_needed"],
        validation_status=(validation or {}).get("validation_status", "SKIPPED"),
        outcome=outcome,
    )
    return {
        "failures": failures,
        "plan": plan,
        "final_status": state.final_status,
        "recovery_attempted": False,
        "recovery_success": False,
    }
