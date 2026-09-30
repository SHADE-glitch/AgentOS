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
            )
            observations_recorded += 1
            # Keep the denormalised count in sync with the observation log.
            store.set_observation_count(memory_id, len(store.list_observations(memory_id=memory_id)))

        candidates_created = 0
        promotion = load_policy("promotion")
        if outcome == "failure":
            store.add_candidate(
                candidate_type="failure",
                loop_id=loop_id,
                payload={"task_id": task_id, "memories_used": memories_used, "quality_score": quality_score},
            )
            candidates_created += 1
        elif outcome == "success" and quality_score >= float(promotion["quality_threshold"]):
            store.add_candidate(
                candidate_type="success",
                loop_id=loop_id,
                payload={"task_id": task_id, "memories_used": memories_used, "quality_score": quality_score},
            )
            candidates_created += 1

        return {"observations_recorded": observations_recorded, "candidates_created": candidates_created}
    finally:
        if owns_store:
            store.close()
