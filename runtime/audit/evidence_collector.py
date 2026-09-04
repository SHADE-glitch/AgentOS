#!/usr/bin/env python3
"""
Validation Evidence Collector — Phase 8.9

Automatically collects evidence for each task execution:

  BEFORE:
    - git status (working tree state)
    - current branch
    - last commit

  AFTER:
    - git diff (changes made)
    - test command executed
    - test stdout
    - test exit code

Output: ~/.agents/reports/{session}/evidence-{task_id}.json

This removes the burden from agents to manually record test evidence.
The collector is called by the runtime before and after each task.
"""

import os
import json
import subprocess
import time
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
REPORTS_DIR = os.path.join(BASE, "reports")


def _session_id():
    return os.environ.get("AOS_SESSION_ID", datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S"))


def _session_dir(session=None):
    sid = session or _session_id()
    d = os.path.join(REPORTS_DIR, sid)
    os.makedirs(d, exist_ok=True)
    return d


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _run(cmd, cwd=None, timeout=30):
    """Run a command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def _git_root(project_root=None):
    """Find the git root for the project."""
    d = project_root or os.getcwd()
    for _ in range(10):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return project_root or os.getcwd()


def collect_before(task_id, project_root=None, loop_id="", session_id=""):
    """
    Collect pre-task evidence: git status, branch, last commit.

    Args:
        task_id: str — task identifier
        project_root: str — path to project repo (defaults to cwd)
        loop_id: str — loop execution identifier
        session_id: str — Phase 10.5: unified session ID

    Returns:
        dict with before evidence
    """
    root = _git_root(project_root)
    branch = ""
    last_commit = ""
    last_commit_msg = ""
    status = ""

    # Git branch
    rc, out, _ = _run(["git", "branch", "--show-current"], cwd=root)
    if rc == 0:
        branch = out.strip()

    # Last commit
    rc, out, _ = _run(["git", "log", "-1", "--format=%H %ai %an"], cwd=root)
    if rc == 0:
        parts = out.strip().split(" ", 2)
        if len(parts) >= 3:
            last_commit = parts[0][:12]
            last_commit_msg = parts[2]

    # Git status (porcelain)
    rc, out, _ = _run(["git", "status", "--porcelain"], cwd=root)
    if rc == 0:
        status = out.strip()

    return {
        "task_id": task_id,
        "loop_id": loop_id,
        "phase": "before",
        "timestamp": _now_iso(),
        "project_root": root,
        "branch": branch,
        "last_commit": last_commit,
        "last_commit_msg": last_commit_msg,
        "git_status": status,
        "working_tree_dirty": bool(status.strip()),
    }


def collect_after(task_id, before_evidence, project_root=None, loop_id="",
                  test_command="", test_stdout="", test_stderr="", test_exit_code=None,
                  session_id=""):
    """
    Collect post-task evidence: git diff, test results.

    Args:
        task_id: str — task identifier
        before_evidence: dict — result from collect_before()
        project_root: str — path to project repo
        loop_id: str — loop execution identifier
        test_command: str — the test command that was run
        test_stdout: str — test stdout
        test_stderr: str — test stderr
        test_exit_code: int — test exit code (0 = pass)
        session_id: str — Phase 10.5: unified session ID

    Returns:
        dict with after evidence
    """
    root = _git_root(project_root)

    # Git diff (staged + unstaged)
    rc, diff_out, _ = _run(["git", "diff", "--stat"], cwd=root)
    diff_stat = diff_out.strip() if rc == 0 else ""

    rc, diff_full, _ = _run(["git", "diff"], cwd=root)
    diff_full = diff_full[:5000] if rc == 0 else ""  # cap at 5000 chars

    # Files changed
    rc, changed_files, _ = _run(["git", "diff", "--name-only"], cwd=root)
    files_changed = changed_files.strip().split("\n") if rc == 0 and changed_files.strip() else []

    # New untracked files
    rc, untracked, _ = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    new_files = untracked.strip().split("\n") if rc == 0 and untracked.strip() else []

    return {
        "task_id": task_id,
        "loop_id": loop_id,
        "phase": "after",
        "timestamp": _now_iso(),
        "project_root": root,
        "diff_stat": diff_stat,
        "diff_summary": diff_full[:2000],
        "files_changed": files_changed,
        "new_files": new_files,
        "test_command": test_command,
        "test_stdout": test_stdout[:5000] if test_stdout else "",
        "test_stderr": test_stderr[:2000] if test_stderr else "",
        "test_exit_code": test_exit_code,
        "test_passed": test_exit_code == 0 if test_exit_code is not None else None,
        "branch": before_evidence.get("branch", ""),
        "before_commit": before_evidence.get("last_commit", ""),
    }


def save_evidence(task_id, before_evidence, after_evidence, session=None, session_id=""):
    """
    Save the complete evidence bundle for a task.

    Args:
        task_id: str — task identifier
        before_evidence: dict — from collect_before()
        after_evidence: dict — from collect_after()
        session: str — optional session ID (legacy)
        session_id: str — Phase 10.5: unified session ID

    Returns:
        str — path to evidence file
    """
    session_dir = _session_dir(session_id or session)

    bundle = {
        "task_id": task_id,
        "session": session or _session_id(),
        "collected_at": _now_iso(),
        "before": before_evidence,
        "after": after_evidence,
        "evidence_version": "1.0",
    }

    evidence_path = os.path.join(session_dir, f"evidence-{task_id}.json")
    with open(evidence_path, "w") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)

    return evidence_path


def get_evidence(task_id, session=None):
    """
    Read evidence for a task.

    Returns:
        dict or None if not found
    """
    session_dir = _session_dir(session)
    evidence_path = os.path.join(session_dir, f"evidence-{task_id}.json")
    if not os.path.exists(evidence_path):
        return None
    with open(evidence_path) as f:
        return json.load(f)


def list_evidence(session=None):
    """
    List all evidence files in a session.

    Returns:
        list of task_ids with evidence
    """
    session_dir = _session_dir(session)
    task_ids = []
    for fname in os.listdir(session_dir):
        if fname.startswith("evidence-") and fname.endswith(".json"):
            tid = fname[len("evidence-"):-len(".json")]
            task_ids.append(tid)
    return sorted(task_ids)


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 evidence_collector.py before <task_id> [project_root]")
        print("  python3 evidence_collector.py after <task_id> [project_root] [test_command] [test_exit_code]")
        print("  python3 evidence_collector.py save <task_id> [project_root]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "before":
        tid = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        root = sys.argv[3] if len(sys.argv) > 3 else None
        ev = collect_before(tid, project_root=root)
        print(json.dumps(ev, indent=2, ensure_ascii=False))

    elif cmd == "after":
        tid = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        root = sys.argv[3] if len(sys.argv) > 3 else None
        tcmd = sys.argv[4] if len(sys.argv) > 4 else ""
        texit = int(sys.argv[5]) if len(sys.argv) > 5 else None
        before = collect_before(tid, project_root=root)
        ev = collect_after(tid, before, project_root=root, test_command=tcmd, test_exit_code=texit)
        print(json.dumps(ev, indent=2, ensure_ascii=False))

    elif cmd == "save":
        tid = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        root = sys.argv[3] if len(sys.argv) > 3 else None
        before = collect_before(tid, project_root=root)
        after = collect_after(tid, before, project_root=root)
        path = save_evidence(tid, before, after)
        print(f"Evidence saved: {path}")