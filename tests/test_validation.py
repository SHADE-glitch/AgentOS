"""Project build detection and code validation tests."""

from __future__ import annotations

import subprocess

import pytest

from aos.core.loop import lifecycle
from aos.core.loop.state import LoopState
from aos.core.validation import code_validator, project_preflight


def _git(path, *args, check=True):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=path,
        check=check,
        capture_output=True,
        text=True,
    )


def _init_repo(path, files=None):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    for name, content in (files or {"app.py": "def main():\n    return 1\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


# ── build detection ────────────────────────────────────────────────────
def test_detect_unknown_build_system(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    result = project_preflight.run_preflight(str(plain))
    assert result.build_system == "unknown"
    assert result.compile_command == ""
    assert result.test_command == ""
    assert result.status == "READY"


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("pom.xml", "maven"),
        ("build.gradle", "gradle"),
        ("build.gradle.kts", "gradle"),
        ("package.json", "npm"),
        ("pyproject.toml", "pip"),
        ("requirements.txt", "pip"),
        ("go.mod", "go"),
    ],
)
def test_detect_build_system(tmp_path, filename, expected):
    project = tmp_path / "proj"
    project.mkdir()
    (project / filename).write_text("", encoding="utf-8")
    system, build_file = project_preflight.detect_build_system(str(project))
    assert system == expected
    assert build_file.endswith(filename)


def test_detect_build_system_in_subdirectory(tmp_path):
    project = tmp_path / "proj"
    (project / "backend").mkdir(parents=True)
    (project / "backend" / "pom.xml").write_text("<project/>", encoding="utf-8")
    system, build_file = project_preflight.detect_build_system(str(project))
    assert system == "maven"
    assert build_file.endswith("backend/pom.xml")


def test_maven_commands_include_build_dir(tmp_path):
    project = tmp_path / "proj"
    (project / "backend").mkdir(parents=True)
    (project / "backend" / "pom.xml").write_text("<project/>", encoding="utf-8")
    result = project_preflight.run_preflight(str(project))
    assert result.compile_command.startswith("cd ")
    assert "mvn compile" in result.compile_command
    assert "mvn test" in result.test_command


def test_python_project_detects_pytest(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    result = project_preflight.run_preflight(str(project))
    assert result.build_system == "pip"
    assert result.runtime == "python"
    assert result.test_command == "pytest"


def test_python_compile_command_is_runnable(tmp_path):
    # Regression: the old command was `python -m py_compile` with no target,
    # which always fails, and `python` may not exist where `python3` does.
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    result = project_preflight.run_preflight(str(project))
    assert result.compile_command == "python3 -m compileall -q ."
    assert code_validator.run_build(result.compile_command, str(project)).status == "PASS"


def test_declared_services_from_docker_compose(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        "services:\n  db:\n    image: mysql:8\n  cache:\n    image: redis:7\n", encoding="utf-8"
    )
    result = project_preflight.run_preflight(str(project))
    names = {s.name for s in result.services}
    assert {"MySQL", "Redis"} <= names
    assert all(s.status == "UNKNOWN" for s in result.services)  # no probing by default


def test_declared_services_from_env_file(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".env").write_text("DATABASE_URL=postgres://localhost/x\nREDIS_HOST=localhost\n", encoding="utf-8")
    result = project_preflight.run_preflight(str(project))
    names = {s.name for s in result.services}
    assert {"PostgreSQL", "Redis"} <= names


def test_project_preflight_result_is_serialisable(tmp_path):
    result = project_preflight.run_preflight(str(tmp_path))
    payload = result.to_dict()
    assert payload["project_root"]
    assert isinstance(payload["services"], list)


# ── code validation ────────────────────────────────────────────────────
def test_git_diff_reports_changes(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "app.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    (repo / "new.py").write_text("x = 1\n", encoding="utf-8")

    is_clean, changes = code_validator.get_git_diff(str(repo))

    assert is_clean is False
    by_path = {c.path: c for c in changes}
    assert by_path["app.py"].status == "modified"
    assert by_path["app.py"].additions == 1
    assert by_path["app.py"].deletions == 1
    assert by_path["new.py"].status == "untracked"


def test_git_diff_on_non_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    is_clean, changes = code_validator.get_git_diff(str(plain))
    assert is_clean is False
    assert changes == []


def test_validation_skipped_without_commands(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    result = code_validator.validate_code_changes(project_root=str(repo))
    assert result.validation_status == "SKIPPED"
    assert result.build_degradation is None


def test_validation_passes_with_passing_commands(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    result = code_validator.validate_code_changes(
        project_root=str(repo), compile_command="true", test_command="true"
    )
    assert result.validation_status == "PASS"
    assert result.build.status == "PASS"
    assert result.test.status == "PASS"


def test_validation_fails_on_failing_build(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    result = code_validator.validate_code_changes(
        project_root=str(repo), compile_command="false", test_command="true"
    )
    assert result.validation_status == "FAIL"
    assert result.build.status == "FAIL"


def test_validation_flags_unexpected_files(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "app.py").write_text("def main():\n    return 3\n", encoding="utf-8")
    result = code_validator.validate_code_changes(
        project_root=str(repo), compile_command="true", test_command="true", expected_files=["other.py"]
    )
    assert result.unexpected_files_changed == 1
    assert result.validation_status == "PARTIAL"


def test_validation_reports_degradation_against_baseline(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    result = code_validator.validate_code_changes(
        project_root=str(repo),
        compile_command="true",
        test_command="false",
        baseline={"test_status": "PASS", "build_status": "PASS"},
    )
    assert result.test_degradation is True
    assert result.validation_status == "FAIL"


def test_validation_runs_each_command_once(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    marker = repo / "runs.txt"
    result = code_validator.validate_code_changes(
        project_root=str(repo), compile_command=f"sh -c 'echo x >> {marker}'"
    )
    assert result.build.status == "PASS"
    assert marker.read_text(encoding="utf-8").count("x") == 1


def test_bug_scanner_hook_is_used(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    result = code_validator.validate_code_changes(
        project_root=str(repo),
        compile_command="true",
        bug_scanner=lambda root: {"total_issues": 2, "critical_count": 1},
    )
    assert result.critical_bug_found is True
    assert result.validation_checks["bug_scan"] == "WARN"


def test_broken_bug_scanner_does_not_fail_validation(tmp_path):
    repo = _init_repo(tmp_path / "repo")

    def boom(root):
        raise RuntimeError("scanner exploded")

    result = code_validator.validate_code_changes(
        project_root=str(repo), compile_command="true", bug_scanner=boom
    )
    assert result.validation_status == "PASS"
    assert result.validation_checks["bug_scan"] == "SKIPPED"


# ── loop integration: validation is not silently skipped ───────────────
def test_loop_records_project_preflight(tmp_path):
    repo = _init_repo(tmp_path / "repo", {"pyproject.toml": "[project]\nname='x'\n"})
    doc = lifecycle.preflight(task="tidy up the project", cwd=str(repo))
    state = LoopState.load(doc["loop_id"])
    preflight = state.stage_data("plan")["project_preflight"]
    assert preflight["build_system"] == "pip"
    assert preflight["test_command"] == "pytest"


def test_run_with_cwd_runs_the_validate_stage(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    doc = lifecycle.run(
        task="add a health check",
        cwd=str(repo),
        provider="test_provider",
        compile_command="true",
        test_command="true",
    )
    state = LoopState.load(doc["loop_id"])
    assert state.stages["validate"]["status"] == "completed"
    assert state.stage_data("validate")["validation_status"] == "PASS"
    assert doc["final_status"] == "completed"


def test_run_without_commands_skips_validation_and_asks(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    doc = lifecycle.run(task="add a health check", cwd=str(repo), provider="test_provider")
    state = LoopState.load(doc["loop_id"])
    assert state.stage_data("validate")["validation_status"] == "SKIPPED"
    assert state.stage_data("validate")["reason"]
    # SKIPPED is absence, not a zero: with nothing else reported the run has no
    # verdict and goes to the label gate instead of being called a completion.
    assert doc["final_status"] == "partial"
    assert doc["learning"]["needs_review"] is True


def test_failing_build_marks_failure(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    doc = lifecycle.run(
        task="add a health check",
        cwd=str(repo),
        provider="test_provider",
        compile_command="false",
    )
    assert doc["final_status"] == "failed"


def test_no_validate_flag_skips(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    doc = lifecycle.run(
        task="add a health check",
        cwd=str(repo),
        provider="test_provider",
        compile_command="true",
        validate=False,
    )
    state = LoopState.load(doc["loop_id"])
    assert state.stage_data("validate")["reason"] == "disabled by request"


def test_no_project_root_means_no_validation_and_no_lie(tmp_path):
    """The engine must not fall back to its own working directory.

    `project_root or "."` meant a host that forgot `cwd` had the CLI detect a
    build system in whatever directory it happened to be launched from, run that
    command, and then hand the result to the learning loop as if it described the
    task. An unnamed project is not a failed project.
    """
    doc = lifecycle.preflight(task="修复 Lua 脚本的过期逻辑", task_id="T1")
    assert doc["classification"]["difficulty"]  # the loop still ran

    result = lifecycle.postflight(task_id=doc["task_id"], loop_id=doc["loop_id"])
    state = LoopState.load(doc["loop_id"])

    assert state.stage_data("validate")["validation_status"] == "SKIPPED"
    assert state.stage_data("validate")["reason"] == "no project root reported"
    assert state.stage_data("plan")["project_preflight"]["status"] == "skipped"
    # Nothing was executed, so nothing is claimed: the run asks instead.
    assert result["final_status"] == "partial"
    assert result["learning"]["needs_review"] is True


def test_an_empty_cwd_string_is_not_a_project_root(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    doc = lifecycle.preflight(task="add a health check", task_id="T1", cwd="")
    result = lifecycle.postflight(task_id=doc["task_id"], loop_id=doc["loop_id"], cwd=str(repo))

    assert result["final_status"] == "partial"
    assert result["learning"]["needs_review"] is True
