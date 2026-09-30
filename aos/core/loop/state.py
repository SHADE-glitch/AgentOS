"""Loop state: the durable record of one preflight -> execute -> postflight run.

The state is the *internal* representation. It is persisted atomically to
``<store>/loops/<loop_id>.json`` so that a host which only calls postflight
(e.g. the OpenCode plugin) can close the learning loop without the engine
having run execution in the same process.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aos.config import get_paths

# Canonical stage order.
STAGES = (
    "route",
    "resolve_role",
    "recall",
    "plan",
    "execute",
    "evidence",
    "validate",
    "record",
    "evolve",
    "finalize",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_loop_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"LOOP-{stamp}-{uuid.uuid4().hex[:4].upper()}"


def new_task_id() -> str:
    return f"HOST-{uuid.uuid4().hex[:6].upper()}"


def _blank_stage() -> dict[str, Any]:
    return {"status": "pending", "started_at": "", "completed_at": "", "error": "", "data": {}}


@dataclass
class LoopState:
    """Mutable state for a single loop."""

    loop_id: str
    task_id: str
    task_text: str
    cwd: str = ""
    session_id: str = ""
    memory_mode: str = "enabled"
    provider: str = "opencode"
    model: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    stage: str = "pending"
    final_status: str = "pending"
    replayed: bool = False
    stages: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {name: _blank_stage() for name in STAGES}
    )
    errors: list[dict[str, Any]] = field(default_factory=list)
    postflight: Optional[dict[str, Any]] = None

    # ── construction ───────────────────────────────────────────────
    @classmethod
    def new(
        cls,
        *,
        task_text: str,
        cwd: str = "",
        session_id: str = "",
        memory_mode: str = "enabled",
        provider: str = "opencode",
        model: str = "",
        task_id: str = "",
        loop_id: str = "",
    ) -> "LoopState":
        return cls(
            loop_id=loop_id or new_loop_id(),
            task_id=task_id or new_task_id(),
            task_text=task_text,
            cwd=cwd,
            session_id=session_id,
            memory_mode=memory_mode,
            provider=provider,
            model=model,
        )

    # ── stage transitions ──────────────────────────────────────────
    def begin(self, stage: str) -> None:
        self.stage = stage
        entry = self.stages.setdefault(stage, _blank_stage())
        entry["status"] = "running"
        entry["started_at"] = now_iso()
        self.updated_at = now_iso()

    def complete(self, stage: str, **data: Any) -> None:
        entry = self.stages.setdefault(stage, _blank_stage())
        entry["status"] = "completed"
        entry["completed_at"] = now_iso()
        if data:
            entry["data"].update(data)
        self.updated_at = now_iso()

    def fail(self, stage: str, error: Any, *, critical: bool = False) -> None:
        entry = self.stages.setdefault(stage, _blank_stage())
        entry["status"] = "failed"
        entry["completed_at"] = now_iso()
        entry["error"] = str(error)
        self.errors.append({"stage": stage, "error": str(error), "critical": critical})
        if critical:
            self.final_status = "failed"
        self.updated_at = now_iso()

    def stage_data(self, stage: str) -> dict[str, Any]:
        return self.stages.get(stage, {}).get("data", {})

    # ── persistence ────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "task_id": self.task_id,
            "task_text": self.task_text,
            "cwd": self.cwd,
            "session_id": self.session_id,
            "memory_mode": self.memory_mode,
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stage": self.stage,
            "final_status": self.final_status,
            "replayed": self.replayed,
            "stages": self.stages,
            "errors": self.errors,
            "postflight": self.postflight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoopState":
        state = cls(
            loop_id=data["loop_id"],
            task_id=data["task_id"],
            task_text=data.get("task_text", ""),
            cwd=data.get("cwd", ""),
            session_id=data.get("session_id", ""),
            memory_mode=data.get("memory_mode", "enabled"),
            provider=data.get("provider", "opencode"),
            model=data.get("model", ""),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
            stage=data.get("stage", "pending"),
            final_status=data.get("final_status", "pending"),
            replayed=bool(data.get("replayed", False)),
            errors=list(data.get("errors", [])),
            postflight=data.get("postflight"),
        )
        for name in STAGES:
            state.stages[name] = {**_blank_stage(), **data.get("stages", {}).get(name, {})}
        return state

    def state_path(self) -> Path:
        return get_paths().loops_dir / f"{self.loop_id}.json"

    def save(self) -> Path:
        """Atomically write the state to disk and return the path."""
        get_paths().ensure_store()
        path = self.state_path()
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)
        return path

    @classmethod
    def load(cls, loop_id: str) -> Optional["LoopState"]:
        path = get_paths().loops_dir / f"{loop_id}.json"
        if not path.is_file():
            return None
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
