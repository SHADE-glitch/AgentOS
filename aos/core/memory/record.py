"""Record loop outcomes into the memory store.

This is the "observe" and "learn" half of one step: a finished loop writes an
observation for the run and for every memory it used, and that evidence becomes
either a *candidate change* to an existing memory or — when nothing was recalled
at all — a proposal for a new one.

Two rules give this module its shape. The first is that **an unlabelled run
proposes nothing**: a verdict the engine guessed at is not evidence for or against
a memory, so a run below the confidence floor writes its observation, asks for a
human label, and generates no candidates until that label arrives. The second is
that a proposal carries its content in the candidate payload and an id reserved
at proposal time, so the learning pipeline can group and review it exactly like a
change to an existing memory, and a human approval is what makes the row real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from aos.core.memory.policy import load_policy
from aos.core.memory.store import MemoryStore, _new_id

# Candidate types that ask for a *new* memory rather than a change to one.
PROPOSAL_TYPES = frozenset({"create", "new", "create_hypothesis"})


def candidate_type_for(outcome: str, quality_score: float, *, promotion: dict[str, Any]) -> Optional[str]:
    """Which change a verdict implies for the memories that were in play.

    ``partial`` yields nothing: "some of it worked" says neither that the recalled
    memories were right nor that they were wrong, and inventing a signal from it
    is how a run that was never labelled came to reinforce everything.
    """
    if outcome == "failure":
        return "weaken"
    if outcome == "success" and float(quality_score) >= float(promotion["quality_threshold"]):
        return "reinforce"
    return None


def should_propose(*, outcome: str, memories_used: list[str], needs_review: bool) -> bool:
    """Whether a run is worth remembering as an episode of its own.

    Two cases, and they are the two the store was blind to before: nothing was
    recalled (so a run that plainly happened could teach it nothing), or the run
    failed (a failure deserves a negative memory even when memories were in play).
    An unlabelled run proposes nothing at all, because its outcome is not yet a
    fact — the label gate is what turns it into one, and it proposes on the way
    through.
    """
    if needs_review:
        return False
    return not memories_used or outcome == "failure"


def proposal_for_loop(
    *,
    loop_id: str,
    task_text: str,
    outcome: str,
    cwd: str = "",
    category: str = "",
    skills: Optional[list[str]] = None,
    files_changed: Optional[list[str]] = None,
    quality_score: float = 0.0,
) -> dict[str, Any]:
    """Draft the episodic memory a run would remember as itself.

    The engine does not summarise with a model, so this is a factual record: what
    was asked, how it was routed, what changed, how it ended. A human reviewing
    the proposal decides whether it is worth keeping as knowledge; the payload is
    what they review, not something injected into the store on its own.
    """
    task = " ".join((task_text or "").split())[:120]
    changed = [str(path) for path in (files_changed or [])][:8]
    body_parts = [f"任务「{task}」的结果：{outcome}。"]
    if category:
        body_parts.append(f"路由：{category}（{', '.join(skills) if skills else '无 skill'}）。")
    if changed:
        body_parts.append("改动：" + ", ".join(changed))
    if cwd:
        body_parts.append(f"位置：{cwd}")
    return {
        "memory_id": _new_id("M"),
        "type": "failure" if outcome == "failure" else "episodic",
        "title": task[:110] or loop_id,
        "body": " ".join(body_parts)[:500],
        "category": category,
        # The route's skills become tags because a tag hit is the largest single
        # term in recall ranking — a proposal tagged "bugfix" can be found again
        # by a bugfix task, which is the whole point of remembering it.
        "tags": sorted({s for s in (skills or []) if s}),
        "roles": [],
        # Scoped to the project it happened in: an episode in one repository is
        # not a fact about another, and an unscoped proposal is how Java advice
        # ends up in a JavaScript task.
        "scope": f"project:{Path(cwd).name}" if cwd else "global",
        "when_to_apply": f"下次处理「{task[:40]}」这类任务时" if task else "",
        "outcome": outcome,
        "quality_score": float(quality_score),
        "loop_id": loop_id,
        "cwd": cwd,
        "skills": list(skills or []),
    }


def add_candidates_for_memories(
    store: MemoryStore,
    *,
    candidate_type: str,
    memories: list[str],
    loop_id: str,
    payload: dict[str, Any],
) -> int:
    """Emit one candidate per memory, for callers that relabel a run later."""
    created = 0
    for memory_id in memories:
        store.add_candidate(
            candidate_type=candidate_type,
            target_memory=memory_id,
            loop_id=loop_id,
            payload=payload,
        )
        created += 1
    return created


def memories_of_loop(store: MemoryStore, loop_id: str) -> list[str]:
    """The memories a finished run had in play, from its observations."""
    seen: list[str] = []
    for row in store.list_observations(loop_id=loop_id):
        memory_id = row.get("memory_id")
        if memory_id and memory_id not in seen:
            seen.append(memory_id)
    return seen


def record_outcome(
    *,
    loop_id: str,
    outcome: str,
    quality_score: float = 0.0,
    task_id: str = "",
    session_id: str = "",
    source_hash: str = "",
    memories_used: Optional[list[str]] = None,
    store: Optional[MemoryStore] = None,
    confidence: float = 1.0,
    signals: Optional[dict[str, Any]] = None,
    needs_review: bool = False,
    synthesised: bool = False,
    skill_used: str = "",
    proposal: Optional[dict[str, Any]] = None,
) -> dict[str, int]:
    """Persist observations for a finished loop, and propose what they imply.

    Returns counts of observations, candidates and proposals written.
    """
    owns_store = store is None
    store = store or MemoryStore()
    try:
        memories_used = [m for m in (memories_used or []) if m]
        snapshot = dict(signals or {})

        # Loop-level observation (always recorded, even with no memories used).
        # It carries the signal snapshot: the run is what a reviewer has to be
        # able to reconstruct, and per-memory rows would only duplicate it.
        store.add_observation(
            loop_id=loop_id,
            outcome=outcome,
            memory_id=None,
            task_id=task_id,
            session_id=session_id,
            quality_score=quality_score,
            source_hash=source_hash,
            confidence=confidence,
            signals=snapshot,
            needs_review=needs_review,
            synthesised=synthesised,
            skill_used=skill_used,
        )
        observations_recorded = 1

        for memory_id in memories_used:
            store.add_observation(
                loop_id=loop_id,
                outcome=outcome,
                memory_id=memory_id,
                task_id=task_id,
                session_id=session_id,
                quality_score=quality_score,
                source_hash=source_hash,
                confidence=confidence,
                synthesised=synthesised,
                skill_used=skill_used,
            )
            observations_recorded += 1
            # Keep the denormalised count in sync with the observation log.
            store.set_observation_count(
                memory_id, len(store.list_observations(memory_id=memory_id))
            )

        candidates_created = 0
        if not needs_review:
            promotion = load_policy("promotion")
            candidate_type = candidate_type_for(outcome, quality_score, promotion=promotion)
            if candidate_type:
                candidates_created += add_candidates_for_memories(
                    store,
                    candidate_type=candidate_type,
                    memories=memories_used,
                    loop_id=loop_id,
                    payload={
                        "task_id": task_id,
                        "outcome": outcome,
                        "quality_score": quality_score,
                        "session_id": session_id,
                        "source_hash": source_hash,
                        "confidence": confidence,
                    },
                )

        proposed = 0
        if proposal and not needs_review:
            store.add_candidate(
                candidate_type="create",
                target_memory=proposal["memory_id"],
                loop_id=loop_id,
                payload={
                    **proposal,
                    "task_id": task_id,
                    "session_id": session_id,
                    "source_hash": source_hash,
                    "proposed": True,
                },
            )
            proposed = 1

        return {
            "observations_recorded": observations_recorded,
            "candidates_created": candidates_created,
            "proposals_created": proposed,
        }
    finally:
        if owns_store:
            store.close()
