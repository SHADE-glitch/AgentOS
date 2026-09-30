"""Session → loop reverse lookup, and the crash record that implies.

opencode's `session.idle` event carries only a `sessionID`. The engine keys every
loop by `loop_id`, so without this mapping a host cannot report the end of a run:
it knows the conversation ended, not which loop to close. That gap is why the
learning signal was missing rather than mis-read — the loop simply never received a
postflight.

The file is also the crash record. `preflight` writes it and `postflight` deletes
it, so an entry that outlives its loop *is* the evidence that a run started and
never reported back — the shape an operator needs to see, and the reason
`store/pending-postflight/` stopped being a directory nothing read or wrote.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aos.config import get_paths

PREFIX = "pending-"
SUFFIX = ".json"


def _safe(session_id: str) -> str:
    """One file per session, and a hostile session id cannot escape the directory.

    Session ids come from the host. `..`, slashes and an empty string all have to
    be inert here rather than deep in a caller that remembers to sanitise.
    """
    cleaned = "".join(ch for ch in str(session_id or "") if ch.isalnum() or ch in "-_")
    return cleaned or "unknown"


def path_for(session_id: str) -> Path:
    return get_paths().pending_dir / f"{PREFIX}{_safe(session_id)}{SUFFIX}"


def record(
    *,
    session_id: str,
    loop_id: str,
    task_id: str = "",
    cwd: str = "",
    task: str = "",
    injected_memories: Optional[list[str]] = None,
    injection_chars: int = 0,
) -> Optional[Path]:
    """Note that a loop opened for this session and owes a postflight.

    A loop with no session cannot be looked up by a host that only knows its
    conversation, so it writes nothing rather than a file nobody can find.
    """
    if not session_id or not loop_id:
        return None
    directory = get_paths().pending_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(session_id)
    payload = {
        "session_id": session_id,
        "loop_id": loop_id,
        "task_id": task_id,
        "cwd": cwd,
        "task": task[:200],
        "injected_memories": list(injected_memories or []),
        "injection_chars": int(injection_chars),
        "since": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def find(session_id: str) -> Optional[dict[str, Any]]:
    path = path_for(session_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # An unreadable record must not resurrect a loop we cannot describe, and
        # must not crash the host's idle handler either.
        return None


def clear(session_id: str) -> bool:
    """Remove the record once the loop has reported back. True if one was there."""
    path = path_for(session_id)
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True


def list_pending() -> list[dict[str, Any]]:
    directory = get_paths().pending_dir
    if not directory.is_dir():
        return []
    entries = []
    for path in sorted(directory.glob(f"{PREFIX}*{SUFFIX}")):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            entries.append({"file": str(path), "unreadable": True})
    return entries


def age_hours(entry: dict[str, Any], *, now: Optional[datetime] = None) -> float:
    """How long a run has been outstanding, for `doctor` to report rather than guess."""
    since = str(entry.get("since") or "")
    if not since:
        return -1.0
    try:
        started = datetime.fromisoformat(since)
    except ValueError:
        return -1.0
    reference = now or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return round((reference - started).total_seconds() / 3600.0, 2)


def summary() -> dict[str, Any]:
    """The counts `doctor --json` reports: outstanding loops, and the oldest."""
    entries = list_pending()
    ages = [age_hours(entry) for entry in entries]
    usable = [age for age in ages if age >= 0]
    return {
        "outstanding": len(entries),
        "unreadable": sum(1 for entry in entries if entry.get("unreadable")),
        "oldest_hours": max(usable) if usable else 0.0,
    }
