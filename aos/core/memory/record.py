"""Record loop outcomes into the memory store.

This is the "observe" step of the learning loop: a finished loop writes
observations for the memories it used, and notable outcomes produce
candidates for the learning pipeline to evaluate later.
"""

from __future__ import annotations

from typing import Any, Optional

from aos.core.memory.policy import load_policy
from aos.core.memory.store import MemoryStore


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
) -> dict[str, int]:
    """Persist observations for a finished loop.

    ``outcome`` is one of ``success`` | ``failure`` | ``partial``.
    Returns counts of observations and candidates written.
    """
    owns_store = store is None
    store = store or MemoryStore()
    try:
        memories_used = [m for m in (memories_used or []) if m]

        # Loop-level observation (always recorded, even with no memories used).
        store.add_observation(
            loop_id=loop_id,
            outcome=outcome,
            memory_id=None,
            task_id=task_id,
            session_id=session_id,
            quality_score=quality_score,
            source_hash=source_hash,
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
            )
            observations_recorded += 1
            # Keep the denormalised count in sync with the observation log.
            store.set_observation_count(memory_id, len(store.list_observations(memory_id=memory_id)))

        # Candidates are *proposed changes to a specific memory*, so the
        # learning pipeline can group and validate them per target. A failure
        # proposes weakening each memory that was in play; a high-quality
        # success proposes reinforcing it.
        promotion = load_policy("promotion")
        candidate_type = None
        if outcome == "failure":
            candidate_type = "weaken"
        elif outcome == "success" and quality_score >= float(promotion["quality_threshold"]):
            candidate_type = "reinforce"

        candidates_created = 0
        if candidate_type:
            for memory_id in memories_used:
                store.add_candidate(
                    candidate_type=candidate_type,
                    target_memory=memory_id,
                    loop_id=loop_id,
                    payload={
                        "task_id": task_id,
                        "outcome": outcome,
                        "quality_score": quality_score,
                        "session_id": session_id,
                        "source_hash": source_hash,
                    },
                )
                candidates_created += 1

        return {"observations_recorded": observations_recorded, "candidates_created": candidates_created}
    finally:
        if owns_store:
            store.close()
