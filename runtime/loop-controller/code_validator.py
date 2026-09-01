#!/usr/bin/env python3
"""
Code Validator — Phase 6.2
Post-execution validation for Agent OS runtime pipeline.

This module validates code changes after OpenCode execution:
  1. Git diff analysis (expected vs unexpected file changes)
  2. Build validation (compile)
  3. Test validation (if tests exist)
  4. Smoke validation (startup check if applicable)

Output: CodeValidationResult with validation status
"""

import os
import subprocess
import yaml
import json
import re
import copy
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


@dataclass
class FileChange:
    path: str
    status: str  # added / modified / deleted / renamed
    additions: int
    deletions: int


@dataclass
class BuildResult:
    command: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    status: str  # PASS / FAIL / TIMEOUT


@dataclass
class TestResult:
    command: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    status: str  # PASS / FAIL / NOT_AVAILABLE / TIMEOUT
    test_classes_found: int
    test_classes_executed: int


@dataclass
class CodeValidationResult:
    execution_id: str
    project_root: str
    validation_status: str  # PASS / FAIL / PARTIAL / BLOCKED
    validated_at: str

    # Git analysis
    git_clean_before: bool
    git_clean_after: bool
    files_changed: List[FileChange]
    expected_files_changed: int
    unexpected_files_changed: int
    only_expected_change: bool

    # Build validation
    build_before: BuildResult
    build_after: BuildResult
    build_degradation: bool  # build passed before but fails after

    # Test validation
    test_before: TestResult
    test_after: TestResult
    test_degradation: bool

    # Overall
    validation_checks: Dict[str, str]

    # Phase 5.1 P0-3: Critical bug detection
    critical_bug_scan: dict = field(default_factory=dict)
    critical_bug_found: bool = False
    notes: List[str] = field(default_factory=list)


def run_command(cmd: str, cwd: str, timeout: int = 300, env: dict = None) -> tuple[int, str, str, int]:
    """Run a shell command and return (exit_code, stdout, stderr, duration_ms)."""
    import time
    import copy

    # Prepare environment
    run_env = copy.deepcopy(os.environ) if env is None else env

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=run_env,
        )
        duration_ms = int((time.time() - start) * 1000)
        return result.returncode, result.stdout, result.stderr, duration_ms
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        return -1, "", f"Command timed out after {timeout}s", duration_ms
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return -1, "", str(e), duration_ms


def get_git_diff(project_root: str) -> tuple[bool, List[FileChange]]:
    """Get git diff status and file changes."""
    # Check if git repo
    exit_code, _, _, _ = run_command("git rev-parse --is-inside-work-tree", project_root, timeout=5)
    if exit_code != 0:
        return False, []

    # Check if clean before
    exit_code, stdout, _, _ = run_command("git status --porcelain", project_root, timeout=5)
    is_clean = exit_code == 0 and stdout.strip() == ""

    # Get diff stats
    exit_code, stdout, _, _ = run_command("git diff --stat", project_root, timeout=10)
    if exit_code != 0:
        return is_clean, []

    changes = []
    for line in stdout.strip().split("\n"):
        if not line or "=>" in line or "file changed" in line:
            continue
        parts = line.split("|")
        if len(parts) == 2:
            path = parts[0].strip()
            stats = parts[1].strip()
            additions = 0
            deletions = 0
            if "+" in stats:
                additions = int(stats.split("+")[0].strip())
            if "-" in stats:
                deletions = int(stats.split("-")[0].strip())
            changes.append(FileChange(
                path=path,
                status="modified",
                additions=additions,
                deletions=deletions,
            ))

    return is_clean, changes


def check_git_status(project_root: str) -> bool:
    """Check if git working directory is clean."""
    exit_code, stdout, _, _ = run_command("git status --porcelain", project_root, timeout=5)
    return exit_code == 0 and stdout.strip() == ""


def run_build(command: str, project_root: str, timeout: int = 300) -> BuildResult:
    """Run build command and return result."""
    # Determine working directory from command
    cwd = project_root
    if command.startswith("cd "):
        parts = command.split("&&")
        if len(parts) > 1:
            cd_part = parts[0].strip()
            # Extract directory from "cd /path/to/dir"
            dir_match = re.match(r"cd\s+(.+)", cd_part)
            if dir_match:
                cwd = dir_match.group(1).strip()
            command = "&&".join(parts[1:]).strip()

    # Set JAVA_HOME for Java projects
    env = copy.deepcopy(os.environ)
    java_home_candidates = [
        "/usr/lib/jvm/java-21-openjdk-amd64",
        "/usr/lib/jvm/java-21-openjdk",
        "/usr/lib/jvm/java-21",
    ]
    for candidate in java_home_candidates:
        if os.path.exists(candidate):
            env["JAVA_HOME"] = candidate
            break

    exit_code, stdout, stderr, duration_ms = run_command(command, cwd, timeout, env=env)
    status = "PASS" if exit_code == 0 else "FAIL"
    if exit_code == -1 and "timed out" in stderr:
        status = "TIMEOUT"
    return BuildResult(
        command=command,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout[:2000],
        stderr=stderr[:2000],
        status=status,
    )


def run_test(command: str, project_root: str, timeout: int = 300) -> TestResult:
    """Run test command and return result."""
    # Determine working directory from command
    cwd = project_root
    if command.startswith("cd "):
        parts = command.split("&&")
        if len(parts) > 1:
            cd_part = parts[0].strip()
            # Extract directory from "cd /path/to/dir"
            dir_match = re.match(r"cd\s+(.+)", cd_part)
            if dir_match:
                cwd = dir_match.group(1).strip()
            command = "&&".join(parts[1:]).strip()

    # Set JAVA_HOME for Java projects
    env = copy.deepcopy(os.environ)
    java_home_candidates = [
        "/usr/lib/jvm/java-21-openjdk-amd64",
        "/usr/lib/jvm/java-21-openjdk",
        "/usr/lib/jvm/java-21",
    ]
    for candidate in java_home_candidates:
        if os.path.exists(candidate):
            env["JAVA_HOME"] = candidate
            break

    exit_code, stdout, stderr, duration_ms = run_command(command, cwd, timeout, env=env)

    # Detect if tests exist
    test_classes_found = 0
    test_classes_executed = 0

    # For Maven, check if tests were actually run
    if "mvn test" in command:
        if "Tests run: 0" in stdout and "Tests run: 0" in stderr:
            test_classes_found = 0
            test_classes_executed = 0
        elif "Tests run:" in stdout:
            m = re.search(r"Tests run:\s*(\d+)", stdout)
            if m:
                test_classes_executed = int(m.group(1))
                test_classes_found = test_classes_executed

    # Determine status
    if exit_code == 0:
        if test_classes_executed == 0:
            status = "NOT_AVAILABLE"
        else:
            status = "PASS"
    else:
        status = "FAIL"

    if exit_code == -1 and "timed out" in stderr:
        status = "TIMEOUT"

    return TestResult(
        command=command,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout[:2000],
        stderr=stderr[:2000],
        status=status,
        test_classes_found=test_classes_found,
        test_classes_executed=test_classes_executed,
    )


def validate_code_changes(
    execution_id: str,
    project_root: str,
    expected_files: List[str],
    compile_command: str = "mvn compile -q",
    test_command: str = "mvn test -q",
    build_timeout: int = 300,
    test_timeout: int = 300,
    run_critical_bug_scan: bool = True,
) -> CodeValidationResult:
    """
    Validate code changes after execution.

    Args:
        execution_id: The execution ID from the runtime
        project_root: Path to the project root
        expected_files: List of expected file paths that should be changed
        compile_command: Command to compile the project
        test_command: Command to run tests
        build_timeout: Timeout for build in seconds
        test_timeout: Timeout for tests in seconds

    Returns:
        CodeValidationResult with validation results
    """
    notes = []
    validation_checks = {}

    # 1. Git diff analysis
    git_clean_before, file_changes = get_git_diff(project_root)
    git_clean_after = check_git_status(project_root)

    # Check expected vs unexpected files
    expected_count = 0
    unexpected_count = 0
    for change in file_changes:
        is_expected = False
        for expected in expected_files:
            if change.path.endswith(expected) or expected in change.path:
                is_expected = True
                break
        if is_expected:
            expected_count += 1
        else:
            unexpected_count += 1

    only_expected = unexpected_count == 0
    validation_checks["git_analysis"] = "PASS" if only_expected else "WARN"
    if unexpected_count > 0:
        notes.append(f"Unexpected file changes: {unexpected_count}")

    # 1.5 Phase 5.1 P0-3: Critical bug detection
    critical_bug_scan = {}
    critical_bug_found = False
    if run_critical_bug_scan:
        try:
            from critical_bug_detector import run_critical_bug_detection, generate_advisory
            bug_result = run_critical_bug_detection(project_root)
            if bug_result.total_issues > 0:
                critical_bug_found = True
                advisories = generate_advisory(bug_result)
                critical_bug_scan = {
                    "total_issues": bug_result.total_issues,
                    "critical_count": bug_result.critical_count,
                    "high_count": bug_result.high_count,
                    "medium_count": bug_result.medium_count,
                    "competing_consumers": [
                        {"queue": c.queue_name, "consumers": c.consumers, "risk": c.risk_level}
                        for c in bug_result.competing_consumers
                    ],
                    "unisolated_dependencies": [
                        {"file": u.file_path, "class": u.class_name, "dependency": u.dependency, "risk": u.risk_level}
                        for u in bug_result.unisolated_dependencies
                    ],
                    "advisories": advisories,
                }
                validation_checks["critical_bug_scan"] = "FAIL" if bug_result.critical_count > 0 else "WARN"
                for adv in advisories:
                    notes.append(adv)
            else:
                validation_checks["critical_bug_scan"] = "PASS"
                notes.append("Critical bug scan: no issues detected")
        except Exception as e:
            notes.append(f"Critical bug scan skipped: {e}")
            validation_checks["critical_bug_scan"] = "SKIPPED"

    # 2. Build before (baseline)
    notes.append("Running baseline build...")
    build_before = run_build(compile_command, project_root, build_timeout)
    validation_checks["build_before"] = build_before.status

    # 3. Build after (validation)
    notes.append("Running post-change build...")
    build_after = run_build(compile_command, project_root, build_timeout)
    validation_checks["build_after"] = build_after.status

    build_degradation = build_before.status == "PASS" and build_after.status == "FAIL"
    if build_degradation:
        notes.append("BUILD DEGRADATION: build passed before but fails after change")
        validation_checks["build_degradation"] = "FAIL"

    # 4. Test before (baseline)
    notes.append("Running baseline tests...")
    test_before = run_test(test_command, project_root, test_timeout)
    validation_checks["test_before"] = test_before.status

    # 5. Test after (validation)
    notes.append("Running post-change tests...")
    test_after = run_test(test_command, project_root, test_timeout)
    validation_checks["test_after"] = test_after.status

    test_degradation = test_before.status == "PASS" and test_after.status == "FAIL"
    if test_degradation:
        notes.append("TEST DEGRADATION: tests passed before but fails after change")
        validation_checks["test_degradation"] = "FAIL"

    # 6. Overall validation
    if build_after.status == "FAIL":
        validation_status = "FAIL"
    elif build_degradation:
        validation_status = "FAIL"
    elif test_degradation:
        validation_status = "FAIL"
    elif not only_expected:
        validation_status = "PARTIAL"
    else:
        validation_status = "PASS"

    return CodeValidationResult(
        execution_id=execution_id,
        project_root=project_root,
        validation_status=validation_status,
        validated_at=datetime.now(timezone.utc).isoformat(),
        git_clean_before=git_clean_before,
        git_clean_after=git_clean_after,
        files_changed=file_changes,
        expected_files_changed=expected_count,
        unexpected_files_changed=unexpected_count,
        only_expected_change=only_expected,
        build_before=build_before,
        build_after=build_after,
        build_degradation=build_degradation,
        test_before=test_before,
        test_after=test_after,
        test_degradation=test_degradation,
        critical_bug_scan=critical_bug_scan,
        critical_bug_found=critical_bug_found,
        validation_checks=validation_checks,
        notes=notes,
    )


def to_dict(result: CodeValidationResult) -> dict:
    """Convert validation result to dict for YAML serialization."""
    return asdict(result)


def to_yaml(result: CodeValidationResult) -> str:
    """Convert validation result to YAML string."""
    return yaml.dump(
        to_dict(result),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 code_validator.py <execution_id> <project_root> [expected_files_json] [compile_command] [test_command]")
        print()
        print("Example:")
        print('  python3 code_validator.py EXEC-123 /home/shade/Public/test \'["InterviewService.java"]\' "cd /home/shade/Public/test/backend && mvn compile -q" "cd /home/shade/Public/test/backend && mvn test -q"')
        sys.exit(1)

    execution_id = sys.argv[1]
    project_root = sys.argv[2]
    expected_files = []
    if len(sys.argv) > 3:
        try:
            expected_files = json.loads(sys.argv[3])
        except json.JSONDecodeError:
            print("WARNING: Invalid expected_files JSON, using empty list")

    compile_command = "mvn compile -q"
    if len(sys.argv) > 4:
        compile_command = sys.argv[4]

    test_command = "mvn test -q"
    if len(sys.argv) > 5:
        test_command = sys.argv[5]

    result = validate_code_changes(
        execution_id,
        project_root,
        expected_files,
        compile_command=compile_command,
        test_command=test_command,
    )

    print("=" * 60)
    print("Code Validation — Phase 6.2")
    print("=" * 60)
    print(to_yaml(result))
    print(f"\nValidation Status: {result.validation_status}")
