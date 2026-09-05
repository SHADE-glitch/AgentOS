#!/usr/bin/env python3
"""
Evidence Collector — Git Linked Worktree Regression Tests (Agent OS Repair #1)

Regression test for the production-observation finding that evidence files were
empty shells with project_root=/home/shade instead of the task worktree.

Root cause: _git_root() only recognized .git DIRECTORIES. A linked git worktree
has a .git FILE (gitdir pointer), so the old walk-up implementation skipped the
worktree root, kept climbing, and stopped at whatever ancestor happened to
contain a .git directory (e.g. a home-directory marker) — returning the WRONG
project_root and producing empty git snapshots.

These tests build REAL git repositories and REAL linked worktrees and assert:

  TEST 1  normal git repository                 → resolved to its own root
  TEST 2  linked worktree (.git is a FILE)      → resolved to the WORKTREE
  TEST 3  explicit project_root is preserved
  TEST 4  nonexistent/invalid root fails clearly (no ancestor fallback)
  TEST 5  git snapshot data actually comes from the specified worktree

Each test embeds the OLD algorithm (legacy_git_root) to prove old=FAIL /
new=PASS, not just string equality.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evidence_collector import _git_root, collect_before, collect_after


# ── helpers ──────────────────────────────────────────────────────

def _git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


def _init_repo(path, filename="file.txt", content="hello\n"):
    """Create a normal git repository with one committed file."""
    os.makedirs(path, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Tester")
    f = os.path.join(path, filename)
    with open(f, "w") as fh:
        fh.write(content)
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _add_linked_worktree(repo, wt_path, decoy_parent=None):
    """
    Add a linked worktree to ``repo`` at ``wt_path``.

    If ``decoy_parent`` is given, it receives a ``.git`` DIRECTORY before the
    worktree is added, reproducing the production bug: the walk-up from the
    worktree (whose own .git is a FILE) would land on the decoy parent's .git
    directory instead of stopping at the worktree.
    """
    os.makedirs(wt_path, exist_ok=False)
    if decoy_parent:
        os.makedirs(os.path.join(decoy_parent, ".git"), exist_ok=True)
    _git(repo, "worktree", "add", "-q", "-b", f"wt-{os.path.basename(wt_path)}", wt_path)
    return wt_path


def _legacy_git_root(project_root=None):
    """The pre-repair implementation (kept here to prove it FAILS the tests)."""
    d = project_root or os.getcwd()
    for _ in range(10):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return project_root or os.getcwd()


# ── TEST 1: normal git repository ────────────────────────────────

def test_normal_repository_resolves_to_itself(tmp_path):
    repo = _init_repo(str(tmp_path / "repo"))

    new_root = _git_root(repo)
    legacy_root = _legacy_git_root(repo)

    assert os.path.isdir(os.path.join(repo, ".git"))       # .git is a directory
    assert new_root == os.path.abspath(repo)
    assert legacy_root == os.path.abspath(repo)            # legacy also fine here


# ── TEST 2: linked worktree, .git is a FILE ──────────────────────

def test_linked_worktree_git_file_resolves_to_worktree(tmp_path):
    base = str(tmp_path)
    repo = _init_repo(os.path.join(base, "golden"))
    wt = _add_linked_worktree(
        repo,
        os.path.join(base, "decoy", "worktrees", "TASK-PO-X"),
        decoy_parent=os.path.join(base, "decoy"),
    )

    # Sanity: linked worktrees carry a .git FILE, not a directory.
    assert os.path.isfile(os.path.join(wt, ".git"))
    assert not os.path.isdir(os.path.join(wt, ".git"))

    new_root = _git_root(wt)
    legacy_root = _legacy_git_root(wt)

    # THE BUG: legacy climbs past the worktree to the decoy parent's .git dir.
    assert legacy_root == os.path.join(base, "decoy")
    assert new_root == os.path.abspath(wt)


# ── TEST 3: explicit project_root is preserved ───────────────────

def test_explicit_project_root_preserved(tmp_path):
    base = str(tmp_path)
    repo = _init_repo(os.path.join(base, "golden"))
    wt = _add_linked_worktree(repo, os.path.join(base, "wt-a"))
    wt2 = _add_linked_worktree(repo, os.path.join(base, "wt-b"))

    # Two sibling worktrees of the same golden repo must resolve to THEMSELVES,
    # not to each other or to the shared golden repo.
    assert _git_root(wt) == os.path.abspath(wt)
    assert _git_root(wt2) == os.path.abspath(wt2)
    assert _git_root(wt) != _git_root(wt2)

    # repo root itself still resolves to the repo.
    assert _git_root(repo) == os.path.abspath(repo)


# ── TEST 4: invalid root fails clearly, no ancestor fallback ─────

def test_nonexistent_project_root_returns_none(tmp_path):
    assert _git_root(str(tmp_path / "does-not-exist")) is None


def test_non_git_dir_with_decoy_ancestor_returns_none(tmp_path):
    # A plain directory whose ancestor contains a .git dir must NOT resolve to
    # that ancestor (legacy behaviour). It is not a repo → explicit None.
    base = str(tmp_path)
    decoy = os.path.join(base, "decoy")
    os.makedirs(os.path.join(decoy, ".git"), exist_ok=True)
    plain = os.path.join(decoy, "plain-not-a-repo")
    os.makedirs(plain, exist_ok=True)

    assert _git_root(plain) is None
    legacy_root = _legacy_git_root(plain)
    assert legacy_root == decoy  # legacy silently falls back — FAIL behaviour


def test_collect_before_returns_repo_resolved_false_for_invalid(tmp_path):
    ev = collect_before("task-1", project_root=str(tmp_path / "missing"))
    assert ev["repo_resolved"] is False
    assert ev["project_root"] == os.path.abspath(str(tmp_path / "missing"))


# ── TEST 5: git snapshot actually comes from the specified worktree ─

def test_git_snapshot_from_worktree_not_golden(tmp_path):
    base = str(tmp_path)
    repo = _init_repo(os.path.join(base, "golden"))
    wt = _add_linked_worktree(repo, os.path.join(base, "wt-a"))

    # Modify a file ONLY in the worktree.
    with open(os.path.join(wt, "file.txt"), "w") as fh:
        fh.write("changed in worktree only\n")

    before = collect_before("TASK-PO-X", project_root=wt)
    after = collect_after("TASK-PO-X", before, project_root=wt)

    # project_root must be the WORKTREE — not /home/shade, not the golden repo.
    assert before["project_root"] == os.path.abspath(wt)
    assert after["project_root"] == os.path.abspath(wt)
    assert before["repo_resolved"] is True
    assert after["repo_resolved"] is True

    # branch and HEAD reflect the worktree's branch.
    assert before["branch"] == f"wt-{os.path.basename(wt)}"

    # The worktree-only modification is visible in git status and diff.
    assert "file.txt" in (before["git_status"] or "")
    assert "file.txt" in after["files_changed"]
    assert "file.txt" in (after["diff_summary"] or "")

    # Cross-check: the GOLDEN repo does not see the worktree's change.
    golden_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "file.txt" not in golden_status
