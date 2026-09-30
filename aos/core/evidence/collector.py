"""Validation evidence collection.

Ported from ``evidence_collector.py``. The behaviour that matters is kept
exactly: ``_git_root`` asks git itself for the repository root, so linked
worktrees (where ``.git`` is a *file* pointing at the real gitdir) resolve
correctly instead of climbing past the worktree to an unrelated ancestor.
When no repository is found the collector reports ``repo_resolved: false``
rather than guessing.

Evidence bundles are written under ``<store>/evidence/<session>/``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aos.config import get_paths

MAX_DIFF = 5000
MAX_TEST_STDOUT = 5000
MAX_TEST_STDERR = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(command: list[str], cwd: Optional[str] = None, timeout: int = 30) -> tuple[int, str, str]:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "command timed out"
    except OSError as exc:
        return -1, "", str(exc)


def git_root(project_root: Optional[str] = None) -> Optional[str]:
    """Resolve the git root owning *project_root*, or None if there is none.

    Handles regular repositories and linked worktrees. Never searches above
    the given path for a different repository.
    """
    directory = os.path.abspath(project_root or os.getcwd())
    if not os.path.isdir(directory):
        return None

    code, out, _ = _run(["git", "-C", directory, "rev-parse", "--show-toplevel"], timeout=15)
    if code == 0 and out.strip():
        return os.path.abspath(out.strip())

    # Fallback for a repo root when git itself is unavailable.
    if os.path.isdir(os.path.join(directory, ".git")):
        return directory
    return None


def session_id() -> str:
    return os.environ.get("AOS_SESSION_ID", "") or datetime.now(timezone.utc).strftime(
        "SESS-%Y%m%d-%H%M%S"
    )


def session_dir(session: str = "") -> Path:
    directory = get_paths().evidence_dir / (session or session_id())
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def collect_before(
    task_id: str, *, project_root: str = "", loop_id: str = "", session: str = ""
) -> dict[str, Any]:
    """Pre-execution snapshot: branch, last commit, working-tree state."""
    root = git_root(project_root)
    base = {
        "task_id": task_id,
        "loop_id": loop_id,
        "phase": "before",
        "timestamp": _now_iso(),
        "session": session or session_id(),
        "project_root": os.path.abspath(project_root) if project_root else "",
    }
    if root is None:
        return {
            **base,
            "repo_resolved": False,
            "branch": "",
            "last_commit": "",
            "last_commit_msg": "",
            "git_status": "",
            "working_tree_dirty": False,
        }

    branch = last_commit = last_commit_msg = status = ""
    code, out, _ = _run(["git", "branch", "--show-current"], cwd=root)
    if code == 0:
        branch = out.strip()

    code, out, _ = _run(["git", "log", "-1", "--format=%H %ai %an"], cwd=root)
    if code == 0:
        parts = out.strip().split(" ", 2)
        if len(parts) >= 3:
            last_commit = parts[0][:12]
            last_commit_msg = parts[2]

    code, out, _ = _run(["git", "status", "--porcelain"], cwd=root)
    if code == 0:
        status = out.strip()

    return {
        **base,
        "repo_resolved": True,
        "project_root": root,
        "branch": branch,
        "last_commit": last_commit,
        "last_commit_msg": last_commit_msg,
        "git_status": status,
        "working_tree_dirty": bool(status.strip()),
    }


def collect_after(
    task_id: str,
    before: dict[str, Any],
    *,
    project_root: str = "",
    loop_id: str = "",
    test_command: str = "",
    test_stdout: str = "",
    test_stderr: str = "",
    test_exit_code: Optional[int] = None,
    session: str = "",
) -> dict[str, Any]:
    """Post-execution snapshot: diff, changed files, test outcome."""
    root = git_root(project_root)
    test_fields = {
        "test_command": test_command,
        "test_stdout": test_stdout[:MAX_TEST_STDOUT],
        "test_stderr": test_stderr[:MAX_TEST_STDERR],
        "test_exit_code": test_exit_code,
        "test_passed": test_exit_code == 0 if test_exit_code is not None else None,
    }
    base = {
        "task_id": task_id,
        "loop_id": loop_id,
        "phase": "after",
        "timestamp": _now_iso(),
        "session": session or session_id(),
        "project_root": os.path.abspath(project_root) if project_root else "",
        "branch": before.get("branch", ""),
        "before_commit": before.get("last_commit", ""),
    }
    if root is None:
        return {
            **base,
            "repo_resolved": False,
            "diff_stat": "",
            "diff_summary": "",
            "files_changed": [],
            "new_files": [],
            **test_fields,
        }

    code, diff_stat, _ = _run(["git", "diff", "--stat"], cwd=root)
    diff_stat = diff_stat.strip() if code == 0 else ""

    code, diff_full, _ = _run(["git", "diff"], cwd=root)
    diff_summary = diff_full[:MAX_DIFF] if code == 0 else ""

    code, changed, _ = _run(["git", "diff", "--name-only"], cwd=root)
    files_changed = changed.strip().split("\n") if code == 0 and changed.strip() else []

    code, untracked, _ = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    new_files = untracked.strip().split("\n") if code == 0 and untracked.strip() else []

    return {
        **base,
        "repo_resolved": True,
        "project_root": root,
        "diff_stat": diff_stat,
        "diff_summary": diff_summary,
        "files_changed": files_changed,
        "new_files": new_files,
        **test_fields,
    }


def save_evidence(
    task_id: str, before: dict[str, Any], after: dict[str, Any], *, session: str = ""
) -> Path:
    """Write the evidence bundle and return its path."""
    directory = session_dir(session or after.get("session", ""))
    bundle = {
        "task_id": task_id,
        "session": session or session_id(),
        "collected_at": _now_iso(),
        "evidence_version": "1.0",
        "before": before,
        "after": after,
    }
    path = directory / f"evidence-{task_id}.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def get_evidence(task_id: str, *, session: str = "") -> Optional[dict[str, Any]]:
    path = session_dir(session) / f"evidence-{task_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_evidence(*, session: str = "") -> list[str]:
    directory = session_dir(session)
    return sorted(
        name[len("evidence-") : -len(".json")]
        for name in os.listdir(directory)
        if name.startswith("evidence-") and name.endswith(".json")
    )
