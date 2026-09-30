"""Policy loading with built-in defaults.

Policies are JSON files under ``content/policies/``. When a file (or key) is
absent, the built-in default is used, so the engine works with an empty
content layer and thresholds are never duplicated as scattered constants.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from aos.config import get_paths

DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "retrieval": {
        "top_k": 5,
        "min_score": 0.15,
        "quality_bonus_weights": {
            "success_rate": 0.15,
            "confidence": 0.10,
            "performance": 0.05,
        },
        "quality_bonus_cap": 0.30,
    },
    "decay": {
        "unused_mild_days": 30,
        "unused_moderate_days": 60,
        "unused_severe_days": 90,
        "factor_mild": 0.9,
        "factor_moderate": 0.7,
        "factor_severe": 0.5,
        "low_success_min_uses": 3,
        "low_success_mild": 0.6,
        "low_success_moderate": 0.4,
        "low_success_severe": 0.2,
        "low_confidence_zero_obs": 0.85,
        "low_confidence_one_obs": 0.90,
        "hypothesis_max_days": 7,
        "hypothesis_factor": 0.7,
        "low_performance_mild_ratio": 0.8,
        "low_performance_severe_ratio": 0.5,
        "low_performance_mild_factor": 0.85,
        "low_performance_severe_factor": 0.7,
    },
    "promotion": {
        "quality_threshold": 3.0,
        "min_observations": 2,
        "hypothesis_min_observations": 1,
        "max_promotions": 5,
    },
    "rejection": {
        # Whether a weakening candidate must be seen by a human. Flipping this to
        # false lets the gate demote memories on its own — the safety property the
        # gate exists for, so it is a switch to pull deliberately, not a default.
        "reject_weaken": True,
        # A proposal for a *new* memory is a human decision regardless of how many
        # runs stand behind it: the alternative is a loop that writes itself.
        "hypothesis_requires_review": True,
    },
    "injection": {
        # The block is one ranked list cut at a whitespace boundary; the
        # ceiling is a character budget, not a token one, so it stays honest
        # without a tokenizer.
        "max_chars": 1400,
        "max_items": 6,
        "max_body_chars": 280,
        "hypothesis_max_items": 1,
    },
    "outcome": {
        # Weight = how much a signal is trusted, and how much coverage a run gets
        # for free. Confidence is the *sum of weights actually observed*, so a
        # host that runs the test suite is believed and one that reports nothing
        # is not. response_summary stays at 0.00: reading the model's own prose
        # for "done" is the signal that made the old quality score meaningless.
        "weights": {
            "test_exit_code": 0.45,
            "build_exit_code": 0.20,
            "validation_status": 0.20,
            "user_interrupted": 0.20,
            "session_error": 0.20,
            "tool_errors": 0.10,
            "todos_unfinished": 0.10,
            "expected_files": 0.10,
            "diff": 0.05,
            "response_summary": 0.00,
        },
        # Lets a deployment re-weight without a code change; a key set to 0.00 here
        # makes that signal contribute nothing to the score and, for the exit-code
        # signals, forfeits its hard-fail veto too — the veto is what the weight
        # buys, so muting a signal the engine still reads would be a silent lie.
        "weight_overrides": {},
        "thresholds": {"success": 0.75, "partial": 0.40},
        "error_cap": 5,
        # A verdict this thin goes to a human rather than into the learning
        # signal. opencode alone reaches ~0.10-0.30 mass, so the intended steady
        # state is that automatic runs queue for `aos review label`.
        "min_auto_confidence": 0.60,
        # Below this coverage the weighted average may not name an outcome at all,
        # in either direction. 0.45 is the weight of the least ambiguous single
        # signal, so one clean test run can be acted on but one empty diff cannot.
        "min_verdict_mass": 0.45,
        # "Not told" is not "failed". Recording a zero-signal run as failure would
        # weaken the memories that were merely present, which is the opposite of
        # what an absence of evidence means.
        "no_signal_outcome": "partial",
        # Quality when there is no score to derive one from: a host that declared
        # success is credited some; an unknown run earns nothing.
        "success_quality": 3.5,
        "partial_quality": 0.0,
        "failure_quality": 0.0,
    },
}


def _policy_path(name: str) -> Path:
    return get_paths().policies_dir / f"{name}.json"


@lru_cache(maxsize=64)
def _read_policy_file(path: Path) -> dict[str, Any]:
    """Read one policy file, memoised by its resolved path.

    Keying on the path rather than the policy name is what stops a changed
    ``AOS_CONTENT_DIR`` from inheriting another root's thresholds. A file
    rewritten in place at the same path still needs :func:`reload`.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_policy(name: str) -> dict[str, Any]:
    """Return the merged policy: built-in defaults overridden by the file."""
    merged = dict(DEFAULT_POLICIES.get(name, {}))
    merged.update(_read_policy_file(_policy_path(name)))
    return merged


def policy_value(name: str, key: str, default: Any = None) -> Any:
    return load_policy(name).get(key, default)


def reload() -> None:
    """Clear cached policy files (needed when one is rewritten in place)."""
    _read_policy_file.cache_clear()
