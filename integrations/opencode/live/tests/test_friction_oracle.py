"""Rig-side measurement tests for the friction oracle.

These are not engine tests: the oracle must never be able to change what Agent OS
records, so it is checked here — in the rig's own test structure — against a fixture
host database. Run explicitly:

    python3 -m pytest integrations/opencode/live/tests -q
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from friction_oracle import (
    VERDICT_FAILURE,
    VERDICT_SUCCESS,
    VERDICT_UNKNOWN,
    build_report,
    connect_host_readonly,
    project_state,
)


def make_host_db(path: Path, steps: list[dict]) -> None:
    """A host-shaped database (message + part) holding the given tool steps in order."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, data TEXT)")
    conn.execute(
        "CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT)"
    )
    conn.execute("CREATE TABLE session (id TEXT, directory TEXT)")
    conn.execute("INSERT INTO session VALUES ('ses_fixture', '/fixture')")
    conn.execute("INSERT INTO message VALUES ('msg_1', 'ses_fixture', 1, '{}')")
    for index, step in enumerate(steps):
        state = {"status": step.get("status", "completed"), "input": {"command": step.get("command", "")},
                 "output": step.get("output", ""), "metadata": dict(step.get("metadata", {}))}
        data = {"type": "tool", "tool": step["tool"], "callID": f"call_{index}", "state": state}
        conn.execute(
            "INSERT INTO part VALUES (?, 'msg_1', 'ses_fixture', ?, ?)",
            (f"prt_{index}", index + 1, json.dumps(data)),
        )
    conn.commit()
    conn.close()


def tool_parts(report: dict) -> list[dict]:
    return report["host_session"]["steps"]


def test_missing_exit_is_unknown_and_never_success(tmp_path):
    db = tmp_path / "host.db"
    make_host_db(db, [
        {"tool": "read", "command": ""},                      # the host stores no exit for readers
        {"tool": "bash", "command": "true", "metadata": {"exit": 0}},
        {"tool": "bash", "command": "false", "metadata": {"exit": 1}},
    ])
    steps = tool_parts(build_report(db, "ses_fixture", project_root=None))
    verdicts = [step["verdict"] for step in steps]
    assert verdicts == [VERDICT_UNKNOWN, VERDICT_SUCCESS, VERDICT_FAILURE]
    assert steps[0]["exit"] is None, "an unread exit must stay absent, not become 0"


def test_a_failing_test_run_behind_a_pipe_is_reported_not_rewritten(tmp_path):
    """LGD-02's real shape: pytest failed, the pipeline's exit is `tail`'s zero."""
    db = tmp_path / "host.db"
    make_host_db(db, [
        {"tool": "bash",
         "command": "python3 -m pytest -q 2>&1 | tail -30",
         "metadata": {"exit": 0},
         "output": "8 failed, 35 passed in 1.44s"},
    ])
    report = build_report(db, "ses_fixture", project_root=None)
    step = tool_parts(report)[0]
    assert step["exit"] == 0, "the oracle states the exit the host recorded, even when it misleads"
    assert step["verdict"] == VERDICT_SUCCESS
    assert step["command_classes"] == ["python3 -m pytest", "tail"], (
        "every segment is named: the plugin's first-segment rule is defect AN, not a fact about shells")
    assert step["test_command"] == "pytest"
    assert step["observed_test_results"] == [{"failed": 8, "passed": 35, "errors": 0}]
    assert report["host_session"]["masked_test_failures"] == [{"seq": 1, "test_command": "pytest",
                                                              "exit": 0, "observed_test_results":
                                                              [{"failed": 8, "passed": 35, "errors": 0}]}], (
        "a step whose test run failed while its exit reads 0 is the measurement this oracle exists for")


def test_one_call_can_hold_the_break_and_the_repair(tmp_path):
    """LGD-02 step 39: a compound that made the fix fail, then restored it and passed."""
    db = tmp_path / "host.db"
    make_host_db(db, [
        {"tool": "bash",
         "command": "cp ledgerd/reporting/monthly.py /tmp/monthly.bak && python3 -m pytest -q 2>&1 | tail -8;"
                    " cp /tmp/monthly.bak ledgerd/reporting/monthly.py && python3 -m pytest -q 2>&1 | tail -2",
         "metadata": {"exit": 0},
         "output": "8 failed, 39 passed in 1.67s\n=== 恢复后 ===\n47 passed in 1.60s"},
    ])
    step = tool_parts(build_report(db, "ses_fixture", project_root=None))[0]
    assert step["observed_test_results"] == [{"failed": 8, "passed": 39, "errors": 0},
                                             {"failed": 0, "passed": 47, "errors": 0}]
    assert step["command_classes"] == ["cp", "python3 -m pytest", "tail", "cp", "python3 -m pytest", "tail"]


def test_a_host_recorded_error_status_is_a_failure_even_without_an_exit(tmp_path):
    db = tmp_path / "host.db"
    make_host_db(db, [{"tool": "skill", "status": "error", "command": ""}])
    step = tool_parts(build_report(db, "ses_fixture", project_root=None))[0]
    assert step["verdict"] == VERDICT_FAILURE


def test_an_unrecognised_command_yields_no_test_result_rather_than_zero(tmp_path):
    db = tmp_path / "host.db"
    make_host_db(db, [{"tool": "bash", "command": "git status", "metadata": {"exit": 0},
                       "output": "On branch master"}])
    step = tool_parts(build_report(db, "ses_fixture", project_root=None))[0]
    assert step["test_command"] is None
    assert step["observed_test_results"] is None, "not parsed is not the same as nothing failed"


def test_commands_and_outputs_never_leave_the_host_database(tmp_path):
    secret_command = "python3 -m ledgerd ingest --file /home/Someone/private.csv --token=SECRET-CMD"
    secret_output = "Traceback: SECRET-OUT in /home/Someone/private.csv"
    db = tmp_path / "host.db"
    make_host_db(db, [{"tool": "bash", "command": secret_command, "metadata": {"exit": 1},
                       "output": secret_output}])
    report = build_report(db, "ses_fixture", project_root=None)
    text = json.dumps(report)
    assert "SECRET-CMD" not in text and "SECRET-OUT" not in text
    assert "/home/Someone" not in text
    step = report["host_session"]["steps"][0]
    assert step["command_classes"] == ["python3 -m ledgerd ingest"], "the shape survives, the values do not"
    assert step["test_command"] is None
    assert step["verdict"] == VERDICT_FAILURE


def test_the_host_database_is_opened_read_only(tmp_path):
    db = tmp_path / "host.db"
    make_host_db(db, [{"tool": "bash", "command": "true", "metadata": {"exit": 0}}])
    conn = connect_host_readonly(db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("UPDATE part SET data = '{}'")


def test_project_state_is_summarised_without_naming_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "base"], check=True)
    (repo / "dirty.py").write_text("x = 1\n", encoding="utf-8")
    report = build_report(_host_with_one_step(tmp_path), "ses_fixture", project_root=repo)
    project = report["project"]
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert project["head"] == head
    assert project["dirty_entries"] == 1
    assert len(project["status_digest"]) == 64
    assert "dirty.py" not in json.dumps(project)


def test_shell_control_words_and_flag_values_are_not_command_names(tmp_path):
    """LGD-06-R2's own classes: `for f in|do|cat|done` and `find f` are noise, not methods."""
    db = tmp_path / "host.db"
    make_host_db(db, [
        {"tool": "bash", "command": 'for f in tests/data/*.csv; do cat "$f"; done', "metadata": {"exit": 0}},
        {"tool": "bash", "command": "find . -maxdepth 1 -type f | sort", "metadata": {"exit": 0}},
    ])
    steps = tool_parts(build_report(db, "ses_fixture", project_root=None))
    assert steps[0]["command_classes"] == ["cat"]
    assert steps[1]["command_classes"] == ["find", "sort"]


def test_a_run_with_no_tool_calls_reports_zero_steps_instead_of_nothing(tmp_path):
    db = tmp_path / "host.db"
    make_host_db(db, [])
    report = build_report(db, "ses_fixture", project_root=None)
    assert report["host_session"]["steps"] == []
    assert report["host_session"]["counts"] == {"tool_parts": 0, VERDICT_SUCCESS: 0, VERDICT_FAILURE: 0,
                                                VERDICT_UNKNOWN: 0}
    assert report["host_session"]["masked_test_failures"] == []


def test_the_git_probe_does_not_take_optional_locks(monkeypatch):
    """`git status` would otherwise refresh the project's index while we measure it."""
    seen: list[dict] = []

    def fake_run(cmd, *args, **kwargs):
        seen.append({"cmd": cmd, "env": kwargs.get("env") or {}})
        completed = subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return completed

    monkeypatch.setattr(subprocess, "run", fake_run)
    project_state(Path("/nonexistent-repo"))
    assert seen, "the probe must go through subprocess.run"
    assert all(call["env"].get("GIT_OPTIONAL_LOCKS") == "0" for call in seen), (
        f"optional locks left on: {seen[0]['env'].get('GIT_OPTIONAL_LOCKS')!r}")


def _host_with_one_step(tmp_path) -> Path:
    db = tmp_path / "host2.db"
    make_host_db(db, [{"tool": "bash", "command": "pytest -q", "metadata": {"exit": 0},
                       "output": "5 passed in 0.10s"}])
    return db
