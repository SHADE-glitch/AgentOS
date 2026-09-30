"""The Agent OS loop: state, stages, lifecycle and team metadata."""

from __future__ import annotations

from aos.core.loop.state import STAGES, LoopState, new_loop_id, new_task_id

__all__ = ["STAGES", "LoopState", "new_loop_id", "new_task_id"]
