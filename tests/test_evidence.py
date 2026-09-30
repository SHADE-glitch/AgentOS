"""Evidence collection, recovery planning and provenance tests."""

from __future__ import annotations

import subprocess

import pytest

from aos.core.evidence import collector, provenance, recovery


def _git(path, *args, check=True):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=path,
        check=check,
        capture_output=True,
        text=True,
    )


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


# ── git root resolution ────────────────────────────────────────────────
def test_git_root_on_regular_repo(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    assert collector.git_root(str(repo)) == str(repo)
    nested = repo / "src"
    nested.mkdir()
    assert collector.git_root(str(nested)) == str(repo)


def test_git_root_on_linked_worktree(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))

    # The linked worktree's .git is a *file*, not a directory.
    assert (worktree / ".git").is_file()
    assert collector.git_root(str(worktree)) == str(worktree)


def test_git_root_returns_none_outside_a_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert collector.git_root(str(plain)) is None


# ── collect / save / load ──────────────────────────────────────────────
def test_collect_before_after_detects_changes(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    before = collector.collect_before("T1", project_root=str(repo), session="S1")
    assert before["repo_resolved"] is True
    assert before["working_tree_dirty"] is False

    (repo / "app.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    after = collector.collect_after(
        "T1", before, project_root=str(repo), session="S1", test_command="pytest", test_exit_code=0
    )
    assert "app.py" in after["files_changed"]
    assert after["test_passed"] is True


def test_collect_reports_unresolved_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    before = collector.collect_before("T1", project_root=str(plain), session="S1")
    assert before["repo_resolved"] is False
    assert before["project_root"] == str(plain)


def test_save_and_get_evidence(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    before = collector.collect_before("T1", project_root=str(repo), session="S1")
    after = collector.collect_after("T1", before, project_root=str(repo), session="S1")
    path = collector.save_evidence("T1", before, after, session="S1")

    assert path.is_file()
    loaded = collector.get_evidence("T1", session="S1")
    assert loaded["task_id"] == "T1"
    assert collector.list_evidence(session="S1") == ["T1"]


# ── recovery planning ──────────────────────────────────────────────────
def test_detect_failures_reports_failed_tests():
    evidence = {"after": {"test_exit_code": 1, "test_command": "pytest", "test_stdout": "boom"}}
    events = recovery.detect_failures(task_id="T1", evidence=evidence)

    assert any(e["type"] == "failed_tests" for e in events)
    assert recovery.has_critical_failures(events)


def test_detect_failures_reports_runtime_error():
    events = recovery.detect_failures(
        task_id="T1", execution={"status": "error", "error": "boom"}, evidence={"after": {}}
    )
    assert events[0]["type"] == "runtime_error"
    assert events[0]["severity"] == "critical"


def test_detect_failures_flags_missing_evidence():
    events = recovery.detect_failures(task_id="T1", evidence=None)
    assert any(e["type"] == "missing_evidence" for e in events)


def test_plan_recovery_never_modifies_code():
    events = recovery.detect_failures(
        task_id="T1",
        execution={"status": "error", "error": "boom"},
        evidence={"after": {"test_exit_code": 1}},
    )
    plan = recovery.plan_recovery(events, task_id="T1")

    assert plan["recovery_needed"] is True
    assert plan["actions"]
    assert all(action["auto_modify_code"] is False for action in plan["actions"])


def test_plan_recovery_is_empty_without_failures():
    plan = recovery.plan_recovery([], task_id="T1")
    assert plan["recovery_needed"] is False
    assert plan["actions"] == []


def test_plan_recovery_marks_retry_exhausted():
    events = recovery.detect_failures(task_id="T1", execution={"status": "error"}, evidence={"after": {}})
    plan = recovery.plan_recovery(events, task_id="T1", retry_count=5)

    assert plan["retry_exhausted"] is True
    assert any(action["action"] == "retry_exhausted" for action in plan["actions"])


# ── provenance ─────────────────────────────────────────────────────────
def test_provenance_for_symbol_has_line_range(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    target = repo / "app.py"
    target.write_text(
        "def main():\n    return 1\n\n\ndef other():\n    return 2\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add other")

    prov = provenance.provenance_for(str(target), symbol="other")

    assert prov["symbol"] == "other"
    assert prov["line_range"] == "L5-L6"
    assert prov["git_commit"]
    assert prov["file_hash"]


def test_provenance_block_is_markdown(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    block = provenance.provenance_block(str(repo / "app.py"), symbol="main")
    assert block.startswith("```provenance")
    assert "file:" in block
