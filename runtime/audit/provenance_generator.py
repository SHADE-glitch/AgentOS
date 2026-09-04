#!/usr/bin/env python3
"""
Provenance Generator — Phase 8.9

Auto-generates file provenance metadata so agents NEVER hand-write line numbers.

Instead of:
  "see line 56 of promoter.py"

Agents should call provenance_for("promoter.py") and reference the auto-generated
symbol, line range, git commit, and diff context.

Output is deterministic, version-controlled, and immune to line drift.

Usage:
  from provenance_generator import provenance_for, provenance_block

  prov = provenance_for("runtime/memory-feedback/promotion/promoter.py", symbol="check_trust_gate")
  # Returns: {file, symbol, line_range, git_commit, git_author, git_date, diff_context}

  block = provenance_block("runtime/loop-controller/loop_controller.py", "run_loop")
  # Returns a markdown-formatted provenance block for inclusion in outputs
"""

import os
import subprocess
import hashlib
from datetime import datetime, timezone

BASE = "/home/shade/.agents"


def _git_root(filepath):
    """Find the git root for a given file path."""
    d = os.path.dirname(os.path.abspath(filepath))
    for _ in range(10):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return BASE


def _run(cmd, cwd=None, timeout=5):
    """Run a command and return stdout or None."""
    try:
        result = subprocess.run(cmd, cwd=cwd or BASE, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _find_symbol_line_range(filepath, symbol):
    """
    Find the line range of a symbol (function/class) in a Python file.

    Uses simple heuristic: find the def/class line, then find the indented block.
    Returns (start_line, end_line) or None.
    """
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception:
        return None

    # Find the symbol definition
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            if symbol in stripped:
                start = i + 1  # 1-based
                break

    if start is None:
        return None

    # Find the end of the block (next line at same or less indentation)
    def_indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    end = start
    for i in range(start, len(lines)):
        line = lines[i]
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= def_indent:
            end = i  # 1-based, the line BEFORE this one
            break
    else:
        end = len(lines)

    return (start, end)


def provenance_for(filepath, symbol=None):
    """
    Generate provenance metadata for a file (and optionally a symbol within it).

    Args:
        filepath: str — path relative to BASE or absolute
        symbol: str — optional function/class name to locate

    Returns:
        dict with keys: file, symbol, line_range, git_commit, git_author, git_date, diff_context, generated_at
    """
    # Resolve absolute path
    if not os.path.isabs(filepath):
        filepath = os.path.join(BASE, filepath)
    filepath = os.path.abspath(filepath)

    rel_path = os.path.relpath(filepath, BASE) if filepath.startswith(BASE) else filepath

    result = {
        "file": rel_path,
        "symbol": symbol or "",
        "line_range": None,
        "git_commit": "",
        "git_author": "",
        "git_date": "",
        "diff_context": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Symbol line range
    if symbol:
        lr = _find_symbol_line_range(filepath, symbol)
        if lr:
            result["line_range"] = f"L{lr[0]}-L{lr[1]}"

    # Git provenance
    git_root = _git_root(filepath)
    rel_to_git = os.path.relpath(filepath, git_root) if git_root else rel_path

    commit = _run(["git", "log", "-1", "--format=%H", "--", rel_to_git], cwd=git_root)
    author = _run(["git", "log", "-1", "--format=%an", "--", rel_to_git], cwd=git_root)
    date = _run(["git", "log", "-1", "--format=%ai", "--", rel_to_git], cwd=git_root)

    if commit:
        result["git_commit"] = commit[:12]
    if author:
        result["git_author"] = author
    if date:
        result["git_date"] = date

    # Diff context (last change to this file)
    diff = _run(["git", "diff", f"{commit}^..{commit}", "--", rel_to_git], cwd=git_root) if commit else ""
    if diff:
        result["diff_context"] = diff[:2000]  # cap at 2000 chars

    # File hash for integrity
    try:
        file_hash = hashlib.md5(result["file"].encode()).hexdigest()[:8]
    except Exception:
        file_hash = "unknown"
    result["file_hash"] = file_hash

    return result


def provenance_block(filepath, symbol=None):
    """
    Generate a markdown-formatted provenance block for inclusion in agent outputs.

    Example output:
    ```provenance
    file: runtime/memory-feedback/promotion/promoter.py
    symbol: check_trust_gate
    range: L45-L72
    commit: abc123def456
    author: Agent OS
    date: 2025-09-03T12:00:00+00:00
    ```
    """
    prov = provenance_for(filepath, symbol)

    lines = ["```provenance"]
    lines.append(f"file: {prov['file']}")
    if prov["symbol"]:
        lines.append(f"symbol: {prov['symbol']}")
    if prov["line_range"]:
        lines.append(f"range: {prov['line_range']}")
    if prov["git_commit"]:
        lines.append(f"commit: {prov['git_commit']}")
    if prov["git_author"]:
        lines.append(f"author: {prov['git_author']}")
    if prov["git_date"]:
        lines.append(f"date: {prov['git_date']}")
    if prov["file_hash"]:
        lines.append(f"file_hash: {prov['file_hash']}")
    lines.append(f"generated_at: {prov['generated_at']}")
    lines.append("```")

    return "\n".join(lines)


def provenance_for_directory(directory, glob_pattern="*.py"):
    """
    Generate provenance for all files matching a glob pattern in a directory.

    Returns:
        list of provenance dicts
    """
    import glob as _glob
    results = []
    pattern = os.path.join(directory, "**", glob_pattern)
    for fpath in _glob.glob(pattern, recursive=True):
        if os.path.isfile(fpath):
            prov = provenance_for(fpath)
            if prov["git_commit"]:
                results.append(prov)
    return results


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python3 provenance_generator.py <filepath> [symbol]")
        print("Example: python3 provenance_generator.py runtime/loop-controller/loop_controller.py run_loop")
        sys.exit(1)

    fpath = sys.argv[1]
    sym = sys.argv[2] if len(sys.argv) > 2 else None
    prov = provenance_for(fpath, sym)
    print(json.dumps(prov, indent=2, ensure_ascii=False))