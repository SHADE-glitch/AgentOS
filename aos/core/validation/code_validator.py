"""Post-execution code validation.

Ported from ``runtime/loop-controller/code_validator.py`` with one real fix:
the original ran the *same* build and test command twice in a row and called
the first result a "before" baseline. Since both runs happened on the
already-modified tree, the degradation check was meaningless. This version
runs each command once and compares against an explicit ``baseline`` the
caller supplies from the pre-execution evidence (or omits the check).

The Java/RabbitMQ-specific critical-bug detector was intentionally not ported;
``bug_scanner`` is a pluggable hook for it (or any other scanner) instead.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

MAX_OUTPUT = 2000


@dataclass
class FileChange:
    path: str
    status: str  # added / modified / deleted / renamed / untracked
    additions: int
    deletions: int


@dataclass
class BuildResult:
    command: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    status: str  # PASS / FAIL / TIMEOUT / SKIPPED


@dataclass
class TestResult:
    command: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    status: str  # PASS / FAIL / TIMEOUT / NOT_AVAILABLE / SKIPPED
    test_classes_found: int = 0
    test_classes_executed: int = 0


@dataclass
class CodeValidationResult:
    execution_id: str
    project_root: str
    validation_status: str  # PASS / FAIL / PARTIAL / BLOCKED / SKIPPED
    validated_at: str
    git_clean_before: bool
    git_clean_after: bool
    files_changed: list[FileChange]
    expected_files_changed: int
    unexpected_files_changed: int
    only_expected_change: bool
    build: BuildResult
    test: TestResult
    build_degradation: Optional[bool]
    test_degradation: Optional[bool]
    validation_checks: dict[str, str] = field(default_factory=dict)
    critical_bug_scan: dict[str, Any] = field(default_factory=dict)
    critical_bug_found: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── process helpers ────────────────────────────────────────────────────
def run_command(command: str, cwd: str, timeout: int = 300) -> tuple[int, str, str, int]:
    """Run a shell command; return ``(exit_code, stdout, stderr, duration_ms)``."""
    start = time.time()
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return result.returncode, result.stdout, result.stderr, int((time.time() - start) * 1000)
    except subprocess.TimeoutExpired:
        return -1, "", f"command timed out after {timeout}s", int((time.time() - start) * 1000)
    except OSError as exc:
        return -1, "", str(exc), int((time.time() - start) * 1000)


def _java_env() -> dict[str, str]:
    env = dict(os.environ)
    if env.get("JAVA_HOME"):
        return env
    for candidate in (
        "/usr/lib/jvm/java-21-openjdk-amd64",
        "/usr/lib/jvm/java-21-openjdk",
        "/usr/lib/jvm/java-21",
    ):
        if os.path.isdir(candidate):
            env["JAVA_HOME"] = candidate
            break
    return env


def _split_cd(command: str, project_root: str) -> tuple[str, str]:
    """Split a ``cd DIR && ...`` command into ``(cwd, command)``."""
    if command.startswith("cd "):
        parts = command.split("&&", 1)
        if len(parts) == 2:
            match = re.match(r"cd\s+(.+)", parts[0].strip())
            if match:
                return match.group(1).strip(), parts[1].strip()
    return project_root, command


def _run_env_command(command: str, project_root: str, timeout: int) -> tuple[int, str, str, int, str]:
    cwd, command = _split_cd(command, project_root)
    start = time.time()
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=_java_env()
        )
        return result.returncode, result.stdout, result.stderr, int((time.time() - start) * 1000), command
    except subprocess.TimeoutExpired:
        return -1, "", f"command timed out after {timeout}s", int((time.time() - start) * 1000), command
    except OSError as exc:
        return -1, "", str(exc), int((time.time() - start) * 1000), command


# ── git analysis ───────────────────────────────────────────────────────
_STATUS_LABELS = {"A": "added", "D": "deleted", "R": "renamed", "?": "untracked"}


def get_git_diff(project_root: str) -> tuple[bool, list[FileChange]]:
    """Return ``(working_tree_clean, changes)`` using porcelain + numstat."""
    code, _, _, _ = run_command("git rev-parse --is-inside-work-tree", project_root, timeout=5)
    if code != 0:
        return False, []

    code, porcelain, _, _ = run_command("git status --porcelain", project_root, timeout=10)
    is_clean = code == 0 and not porcelain.strip()

    counts: dict[str, tuple[int, int]] = {}
    code, numstat, _, _ = run_command("git diff --numstat", project_root, timeout=10)
    if code == 0:
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                additions = int(parts[0]) if parts[0].isdigit() else 0
                deletions = int(parts[1]) if parts[1].isdigit() else 0
                counts[parts[2]] = (additions, deletions)

    changes: list[FileChange] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        code_xy, path = line[:2], line[3:].strip()
        if " -> " in path:  # rename: "old -> new"
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if code_xy == "??":
            label = "untracked"
        else:
            label = _STATUS_LABELS.get(code_xy.strip()[:1], "modified")
        additions, deletions = counts.get(path, (0, 0))
        changes.append(FileChange(path=path, status=label, additions=additions, deletions=deletions))

    return is_clean, changes


def check_git_status(project_root: str) -> bool:
    """True when the working tree is clean."""
    code, out, _, _ = run_command("git status --porcelain", project_root, timeout=5)
    return code == 0 and not out.strip()


# ── build / test ───────────────────────────────────────────────────────
def run_build(command: str, project_root: str, timeout: int = 300) -> BuildResult:
    if not command:
        return BuildResult(command="", exit_code=0, duration_ms=0, stdout="", stderr="", status="SKIPPED")
    code, out, err, duration_ms, resolved = _run_env_command(command, project_root, timeout)
    if code == -1 and "timed out" in err:
        status = "TIMEOUT"
    elif code == 0:
        status = "PASS"
    else:
        status = "FAIL"
    return BuildResult(
        command=resolved, exit_code=code, duration_ms=duration_ms,
        stdout=out[:MAX_OUTPUT], stderr=err[:MAX_OUTPUT], status=status,
    )


def run_test(command: str, project_root: str, timeout: int = 300) -> TestResult:
    if not command:
        return TestResult(command="", exit_code=0, duration_ms=0, stdout="", stderr="", status="SKIPPED")
    code, out, err, duration_ms, resolved = _run_env_command(command, project_root, timeout)

    found = executed = 0
    if "mvn test" in resolved and "Tests run:" in out:
        match = re.search(r"Tests run:\s*(\d+)", out)
        if match:
            executed = int(match.group(1))
            found = executed

    if code == -1 and "timed out" in err:
        status = "TIMEOUT"
    elif code != 0:
        status = "FAIL"
    elif "mvn test" in resolved and executed == 0:
        status = "NOT_AVAILABLE"
    else:
        status = "PASS"
    return TestResult(
        command=resolved, exit_code=code, duration_ms=duration_ms,
        stdout=out[:MAX_OUTPUT], stderr=err[:MAX_OUTPUT], status=status,
        test_classes_found=found, test_classes_executed=executed,
    )


# ── validation ─────────────────────────────────────────────────────────
def validate_code_changes(
    *,
    project_root: str,
    execution_id: str = "",
    expected_files: Optional[list[str]] = None,
    compile_command: str = "",
    test_command: str = "",
    build_timeout: int = 300,
    test_timeout: int = 300,
    baseline: Optional[dict[str, Any]] = None,
    bug_scanner: Optional[Callable[[str], dict[str, Any]]] = None,
) -> CodeValidationResult:
    """Validate the current changes in *project_root*.

    ``baseline`` may carry ``build_status`` / ``test_status`` observed before
    execution; degradation is only reported when a baseline is supplied.
    """
    expected_files = expected_files or []
    notes: list[str] = []
    checks: dict[str, str] = {}

    git_clean_before, changes = get_git_diff(project_root)
    git_clean_after = check_git_status(project_root)

    expected_count = sum(
        1 for change in changes if any(e and (change.path.endswith(e) or e in change.path) for e in expected_files)
    )
    unexpected_count = len(changes) - expected_count
    only_expected = unexpected_count == 0
    checks["git_analysis"] = "PASS" if only_expected else "WARN"
    if unexpected_count:
        notes.append(f"{unexpected_count} unexpected file change(s)")

    critical_scan: dict[str, Any] = {}
    critical_found = False
    if bug_scanner is not None:
        try:
            critical_scan = bug_scanner(project_root) or {}
            critical_found = bool(critical_scan.get("total_issues"))
            checks["bug_scan"] = "WARN" if critical_found else "PASS"
        except Exception as exc:  # a broken scanner must not fail validation
            notes.append(f"bug scan skipped: {exc}")
            checks["bug_scan"] = "SKIPPED"

    if not compile_command and not test_command:
        notes.append("no compile or test command supplied; validation skipped")
        checks["validation"] = "SKIPPED"
        return CodeValidationResult(
            execution_id=execution_id,
            project_root=os.path.abspath(project_root),
            validation_status="SKIPPED",
            validated_at=datetime.now(timezone.utc).isoformat(),
            git_clean_before=git_clean_before,
            git_clean_after=git_clean_after,
            files_changed=changes,
            expected_files_changed=expected_count,
            unexpected_files_changed=unexpected_count,
            only_expected_change=only_expected,
            build=BuildResult("", 0, 0, "", "", "SKIPPED"),
            test=TestResult("", 0, 0, "", "", "SKIPPED"),
            build_degradation=None,
            test_degradation=None,
            validation_checks=checks,
            critical_bug_scan=critical_scan,
            critical_bug_found=critical_found,
            notes=notes,
        )

    build = run_build(compile_command, project_root, build_timeout)
    checks["build"] = build.status
    test = run_test(test_command, project_root, test_timeout)
    checks["test"] = test.status

    baseline = baseline or {}
    build_degradation = None
    if baseline.get("build_status") is not None:
        build_degradation = baseline["build_status"] == "PASS" and build.status == "FAIL"
    test_degradation = None
    if baseline.get("test_status") is not None:
        test_degradation = baseline["test_status"] == "PASS" and test.status == "FAIL"
    if build_degradation:
        notes.append("BUILD DEGRADATION: build passed before and fails now")
    if test_degradation:
        notes.append("TEST DEGRADATION: tests passed before and fail now")

    if build.status == "FAIL" or build_degradation or test_degradation:
        validation_status = "FAIL"
    elif not only_expected:
        validation_status = "PARTIAL"
    else:
        validation_status = "PASS"

    return CodeValidationResult(
        execution_id=execution_id,
        project_root=os.path.abspath(project_root),
        validation_status=validation_status,
        validated_at=datetime.now(timezone.utc).isoformat(),
        git_clean_before=git_clean_before,
        git_clean_after=git_clean_after,
        files_changed=changes,
        expected_files_changed=expected_count,
        unexpected_files_changed=unexpected_count,
        only_expected_change=only_expected,
        build=build,
        test=test,
        build_degradation=build_degradation,
        test_degradation=test_degradation,
        validation_checks=checks,
        critical_bug_scan=critical_scan,
        critical_bug_found=critical_found,
        notes=notes,
    )
