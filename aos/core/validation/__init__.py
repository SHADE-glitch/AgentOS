"""Project build detection and post-execution code validation."""

from __future__ import annotations

from aos.core.validation import code_validator, project_preflight
from aos.core.validation.code_validator import CodeValidationResult, validate_code_changes
from aos.core.validation.project_preflight import ProjectPreflightResult, run_preflight

__all__ = [
    "CodeValidationResult",
    "ProjectPreflightResult",
    "code_validator",
    "project_preflight",
    "run_preflight",
    "validate_code_changes",
]
