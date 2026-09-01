#!/usr/bin/env python3
"""
Regression Tests — code_validator.py (Python 3.14 Compatibility)

Verifies:
  1. CodeValidationResult import succeeds on Python 3.14
  2. CodeValidationResult instantiation succeeds
  3. Field ordering is correct (no default args before non-default)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from code_validator import (
    CodeValidationResult,
    FileChange,
    BuildResult,
    TestResult,
)


class TestCodeValidatorImport(unittest.TestCase):
    """Verify code_validator.py imports correctly on Python 3.14."""

    def test_import_code_validation_result(self):
        """CodeValidationResult dataclass must import without TypeError."""
        self.assertIsNotNone(CodeValidationResult)

    def test_import_file_change(self):
        """FileChange dataclass must import."""
        self.assertIsNotNone(FileChange)

    def test_import_build_result(self):
        """BuildResult dataclass must import."""
        self.assertIsNotNone(BuildResult)

    def test_import_test_result(self):
        """TestResult dataclass must import."""
        self.assertIsNotNone(TestResult)


class TestCodeValidationResultInstantiation(unittest.TestCase):
    """Verify CodeValidationResult can be instantiated."""

    def setUp(self):
        self.build_pass = BuildResult(
            command="mvn compile -q",
            exit_code=0,
            duration_ms=1500,
            stdout="BUILD SUCCESS",
            stderr="",
            status="PASS",
        )
        self.test_pass = TestResult(
            command="mvn test",
            exit_code=0,
            duration_ms=3000,
            stdout="Tests run: 10, Failures: 0",
            stderr="",
            status="PASS",
            test_classes_found=5,
            test_classes_executed=5,
        )

    def test_minimal_instantiation(self):
        """Minimal required fields must produce a valid instance."""
        result = CodeValidationResult(
            execution_id="TEST-001",
            project_root="/tmp/test",
            validation_status="PASS",
            validated_at="2026-01-01T00:00:00Z",
            git_clean_before=True,
            git_clean_after=True,
            files_changed=[],
            expected_files_changed=0,
            unexpected_files_changed=0,
            only_expected_change=True,
            build_before=self.build_pass,
            build_after=self.build_pass,
            build_degradation=False,
            test_before=self.test_pass,
            test_after=self.test_pass,
            test_degradation=False,
            validation_checks={"import": "pass", "instantiation": "pass"},
        )
        self.assertEqual(result.validation_status, "PASS")
        self.assertEqual(result.execution_id, "TEST-001")
        self.assertEqual(result.validation_checks["import"], "pass")

    def test_with_critical_bug_detection(self):
        """With critical bug fields populated."""
        result = CodeValidationResult(
            execution_id="TEST-002",
            project_root="/tmp/test",
            validation_status="FAIL",
            validated_at="2026-01-01T00:00:00Z",
            git_clean_before=True,
            git_clean_after=True,
            files_changed=[],
            expected_files_changed=0,
            unexpected_files_changed=0,
            only_expected_change=True,
            build_before=self.build_pass,
            build_after=self.build_pass,
            build_degradation=False,
            test_before=self.test_pass,
            test_after=self.test_pass,
            test_degradation=False,
            validation_checks={"critical_bug": "found"},
            critical_bug_found=True,
            critical_bug_scan={"competing_consumers": 1, "unisolated_dependencies": 2},
        )
        self.assertTrue(result.critical_bug_found)
        self.assertEqual(result.critical_bug_scan["competing_consumers"], 1)

    def test_default_values(self):
        """Defaults should be populated when not explicitly provided."""
        result = CodeValidationResult(
            execution_id="TEST-003",
            project_root="/tmp/test",
            validation_status="PASS",
            validated_at="2026-01-01T00:00:00Z",
            git_clean_before=True,
            git_clean_after=True,
            files_changed=[],
            expected_files_changed=0,
            unexpected_files_changed=0,
            only_expected_change=True,
            build_before=self.build_pass,
            build_after=self.build_pass,
            build_degradation=False,
            test_before=self.test_pass,
            test_after=self.test_pass,
            test_degradation=False,
            validation_checks={"check": "ok"},
        )
        self.assertFalse(result.critical_bug_found)
        self.assertEqual(result.critical_bug_scan, {})
        self.assertEqual(result.notes, [])

    def test_with_file_changes(self):
        """With file changes list populated."""
        changes = [
            FileChange(path="src/Main.java", status="modified", additions=5, deletions=2),
            FileChange(path="src/New.java", status="added", additions=20, deletions=0),
        ]
        result = CodeValidationResult(
            execution_id="TEST-004",
            project_root="/tmp/test",
            validation_status="PARTIAL",
            validated_at="2026-01-01T00:00:00Z",
            git_clean_before=True,
            git_clean_after=False,
            files_changed=changes,
            expected_files_changed=1,
            unexpected_files_changed=1,
            only_expected_change=False,
            build_before=self.build_pass,
            build_after=self.build_pass,
            build_degradation=False,
            test_before=self.test_pass,
            test_after=self.test_pass,
            test_degradation=False,
            validation_checks={"git": "unexpected_changes"},
        )
        self.assertEqual(len(result.files_changed), 2)
        self.assertEqual(result.unexpected_files_changed, 1)
        self.assertFalse(result.only_expected_change)


if __name__ == "__main__":
    unittest.main()