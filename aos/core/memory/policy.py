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
        "reject_create_hypothesis": True,
        "reject_weaken": True,
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
