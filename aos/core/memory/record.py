"""Record loop outcomes into the memory store.

This is the "observe" step: a finished run writes **one** loop-level
observation, and that verdict is what later becomes a candidate change to an
existing memory or — when nothing was recalled — a proposal for a new one.

Three rules give this module its shape.

**Linkage is not outcome.** Being retrieved into a run says only that a memory
was in the room. The per-memory observation rows this module used to write for
every recalled memory were read back as that memory's success rate, so a memory
rose in the ranking the more often it was recalled (R-006). Recall is now logged
once, in ``retrieval_log``, and the only thing that may credit or blame a memory
is an *attributed* verdict: the host reported having used the very subject the
memory is about. No attribution, no candidate.

**An unlabelled run proposes nothing**: a verdict the engine guessed at is not
evidence for or against a memory, so a run below the confidence floor writes its
observation, asks for a human label, and generates no candidates until that
label arrives. A human label is attribution by definition, which is why the
label path (``evolve``) keeps naming the memories involved.

**A proposal carries its content in the candidate payload** and an id reserved
at proposal time, so the learning pipeline can group and review it exactly like
a change to an existing memory, and a human approval is what makes the row real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from aos.core.learning import identity
from aos.core.memory.policy import load_policy
from aos.core.memory.store import MemoryStore

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


def _clip(text: Any, limit: int) -> str:
    """Cut for display without pretending the cut did not happen.

    A silent `[:40]` turned a truncated claim into a claim that reads as finished — the draft's
    `when_to_apply` ended mid-token and the injected line asserted something nobody wrote. Latin
    backs off to a word boundary; CJK has none, so it gets the marker and the reader sees the seam.
    """
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit]
    if cut[-1:].isascii() and cut[-1:].isalpha() and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ，,、。;；:：") + "…"


# Signals that state a fact about how a run ended, each with the phrase it earns.
# `response_summary` is deliberately absent: the model's own prose is material a human may read
# when approving, never a fact this draft asserts — the same reason its verdict weight is 0.00.
_SIGNAL_PHRASES = (
    ("tool_errors", "工具错误 {n}"),
    ("test_exit_code", "测试退出码 {v}"),
    ("build_exit_code", "构建退出码 {v}"),
    ("validation_status", "校验 {v}"),
    ("todos_unfinished", "未完成 todo {n}"),
    ("expected_files", "期望改动 {n} 个文件"),
    ("user_interrupted", "用户中断"),
    ("session_error", "硬失败：session_error"),
)

# Reported, and says nothing: an absent-in-name-only signal that should not read as a fact.
_NOTHING_REPORTED = {"tool_errors", "user_interrupted", "session_error", "todos_unfinished"}

_OUTCOME_LEAD = {"failure": "失败于", "partial": "部分完成于", "success": "完成于"}

_HOLE = {
    "failure": "未归因：为什么失败 —— 信号里没有原因，这一句要人补。",
    "partial": "未归因：哪一半没做到 —— 信号里没有，这一句要人补。",
    "success": "未归因：为什么这次成了 —— 信号里没有原因，这一句要人补。",
}


def _distil(signals: Optional[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Split the reported signals into facts worth writing and holes worth naming."""
    given = dict(signals or {})
    facts: list[str] = []
    not_reported: list[str] = []
    for key, phrase in _SIGNAL_PHRASES:
        if key not in given or given[key] is None:
            not_reported.append(key)
            continue
        value = given[key]
        if value in (0, False, [], {}, "") and key in _NOTHING_REPORTED:
            continue  # reported, and the report is "none" — not a fact, not a hole
        if isinstance(value, (list, tuple)):
            rendered = phrase.format(n=len(value), v=len(value))
        elif isinstance(value, bool):
            rendered = phrase.format(n=1, v="")
        else:
            rendered = phrase.format(n=value, v=value)
        facts.append(rendered.rstrip())
    return facts, not_reported


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
    signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Draft the episodic memory a run would remember as itself.

    The engine summarises with no model, so this is a factual record — and only a factual record.
    Defect AG was that the previous draft echoed the question and called it a lesson: the approved
    row read `任务「…」的结果：failure。 路由：report。 位置：…`, and because `inject` renders
    `type='failure'` behind `不要：`, the next prompt was told "不要：<an incident line>" where the
    promise this layer makes is `不要…因为…`. There is no `因为` in any signal, and inventing one is
    how a store fills itself with plausible noise.

    So the draft now states what the signals prove, names what they do not, and marks the missing
    cause as a hole for the human to fill at approval time. Nothing here decides the lesson.
    """
    task = " ".join((task_text or "").split())
    changed = [str(path) for path in (files_changed or [])][:8]
    facts, not_reported = _distil(signals)

    parts = [f'{_OUTCOME_LEAD.get(outcome, "结束于")}「{_clip(task, 80)}」']
    if category:
        parts.append(f"路由 {category}" + (f"（技能 {'、'.join(s for s in skills if s)}）" if skills else ""))
    if changed:
        parts.append(f"改动 {len(changed)} 个文件（{'、'.join(changed)}）")
    if facts:
        parts.append("可证：" + "、".join(facts))

    # The hole is reserved, not appended and hoped-for: the body is capped, and a long file list
    # with every signal reported used to slice the sentence off the end — leaving a draft that
    # asserted an incident and named nothing missing, which is the same silence as the old echo.
    hole = _HOLE.get(outcome, "未归因：原因不在信号里，要人补一句。")
    head = " ".join(parts)
    budget = 500 - len(hole) - 1
    if not_reported:
        gaps = f"缺证：{'、'.join(not_reported)} 未上报"
        if len(head) + len(gaps) + 1 <= budget:
            head = f"{head} {gaps}"
    if len(head) > budget:
        head = _clip(head, budget)
    body = f"{head} {hole}"
    mtype = "failure" if outcome == "failure" else "episodic"
    scope = f"project:{Path(cwd).name}" if cwd else "global"
    title = _clip(task, 110) or loop_id
    where = f"在 {Path(cwd).name} 里" if cwd else ""
    return {
        # Derived from what the episode says, not handed out randomly: the same
        # task failing three times is one thing worth remembering once, and a
        # stable id is what lets the review queue recognise the second arrival
        # instead of opening a third decision for a human to make again.
        "memory_id": identity.proposal_id(
            scope=scope, category=category, mtype=mtype, title=title, body=body
        ),
        "type": mtype,
        "title": title,
        "body": body,
        "category": category,
        # The route's skills become tags because a tag hit is the largest single
        # term in recall ranking — a proposal tagged "bugfix" can be found again
        # by a bugfix task, which is the whole point of remembering it.
        "tags": sorted({s for s in (skills or []) if s}),
        "roles": [],
        # Scoped to the project it happened in: an episode in one repository is
        # not a fact about another, and an unscoped proposal is how Java advice
        # ends up in a JavaScript task.
        "scope": scope,
        "when_to_apply": f"下次{where}处理「{_clip(task, 48)}」这类任务时" if task else "",
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
    """The memories a finished run had in play, from the retrieval log."""
    return store.memories_retrieved_in_loop(loop_id)


def is_attributable(memory: dict[str, Any], skill_used: str) -> bool:
    """Whether a run's verdict may be credited or blamed to this memory.

    The host's reported skill is the only causal signal the contract carries, so
    it has to line up with what the memory is about — its category or one of its
    tags. A memory that merely shared context with a failure is not implicated by
    it; that inference used to be made automatically, and it is the exact shape
    of the positive feedback the research records call linkage-not-outcome.
    """
    skill = " ".join((skill_used or "").lower().replace("/", " ").replace("-", " ").split())
    if not skill:
        return False
    subjects = {str(memory.get("category") or "").lower()}
    subjects |= {str(tag).lower() for tag in (memory.get("tags") or [])}
    subjects.discard("")
    for subject in subjects:
        needle = " ".join(subject.replace("/", " ").replace("-", " ").split())
        if needle and (needle in skill or skill in needle):
            return True
    return False


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
        # Linkage is already on record in retrieval_log (written by recall);
        # per-memory observation rows are gone, so nothing here re-writes the
        # same run once per memory and then averages it back as their merit.
        observations_recorded = 1
        for memory_id in memories_used:
            store.set_observation_count(memory_id, store.linked_outcome_count(memory_id))

        candidates_created = 0
        if not needs_review:
            promotion = load_policy("promotion")
            candidate_type = candidate_type_for(outcome, quality_score, promotion=promotion)
            rows = {m["memory_id"]: m for m in store.memories_for_scoring()}
            attributed = [
                memory_id
                for memory_id in memories_used
                if is_attributable(rows.get(memory_id) or {}, skill_used)
            ] if candidate_type else []
            if attributed:
                candidates_created += add_candidates_for_memories(
                    store,
                    candidate_type=candidate_type,
                    memories=attributed,
                    loop_id=loop_id,
                    payload={
                        "task_id": task_id,
                        "outcome": outcome,
                        "quality_score": quality_score,
                        "session_id": session_id,
                        "source_hash": source_hash,
                        "confidence": confidence,
                        "skill_used": skill_used,
                        # Recorded so a reviewer can see why this memory is being
                        # credited or blamed, rather than having to guess that it
                        # was merely in context.
                        "attributed_by": f"skill_used={skill_used}",
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
