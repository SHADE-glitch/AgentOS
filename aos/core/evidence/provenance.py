"""Deterministic file/symbol provenance.

Ported from ``provenance_generator.py``. Agents reference ``provenance_for()``
instead of hand-writing line numbers, so references do not drift. The git root
is resolved with the worktree-aware helper from :mod:`aos.core.evidence.collector`
rather than the original's ``.git``-directory walk.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aos.config import get_paths
from aos.core.evidence.collector import git_root

MAX_DIFF = 2000


def _run(command: list[str], cwd: Optional[str] = None, timeout: int = 5) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _symbol_line_range(path: Path, symbol: str) -> Optional[tuple[int, int]]:
    """Line range of a top-level ``def``/``class`` containing *symbol*."""
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith("def ") or stripped.startswith("class ")) and symbol in stripped:
            start = index + 1  # 1-based
            break
    if start is None:
        return None

    def_indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        if (len(line) - len(line.lstrip())) <= def_indent:
            end = index  # 1-based line before this one
            break
    return start, end


def provenance_for(filepath: str, symbol: Optional[str] = None) -> dict[str, Any]:
    """Provenance metadata for a file (and optionally a symbol within it)."""
    root = get_paths().root
    path = Path(filepath)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        rel_path = str(path.relative_to(root))
    except ValueError:
        rel_path = str(path)

    result: dict[str, Any] = {
        "file": rel_path,
        "symbol": symbol or "",
        "line_range": None,
        "git_commit": "",
        "git_author": "",
        "git_date": "",
        "diff_context": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if symbol:
        line_range = _symbol_line_range(path, symbol)
        if line_range:
            result["line_range"] = f"L{line_range[0]}-L{line_range[1]}"

    repo = git_root(str(path.parent))
    rel_to_git = str(path.relative_to(repo)) if repo and str(path).startswith(repo) else rel_path
    if repo:
        commit = _run(["git", "log", "-1", "--format=%H", "--", rel_to_git], cwd=repo)
        if commit:
            result["git_commit"] = commit[:12]
            result["git_author"] = _run(["git", "log", "-1", "--format=%an", "--", rel_to_git], cwd=repo)
            result["git_date"] = _run(["git", "log", "-1", "--format=%ai", "--", rel_to_git], cwd=repo)
            diff = _run(["git", "diff", f"{commit}^..{commit}", "--", rel_to_git], cwd=repo)
            result["diff_context"] = diff[:MAX_DIFF]

    result["file_hash"] = hashlib.md5(result["file"].encode("utf-8")).hexdigest()[:8]
    return result
