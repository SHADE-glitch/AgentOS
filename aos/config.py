"""Central configuration and path resolution for the Agent OS engine.

The engine is repository-root relative by default so that it runs and is
testable in-place. Every path is overridable through environment variables,
and no module outside this file may hardcode an install location.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when the Agent OS root cannot be resolved."""


# Environment variables recognised by the engine.
ENV_ROOT = "AGENT_OS_ROOT"
ENV_STORE_DIR = "AOS_STORE_DIR"
ENV_DB_PATH = "AOS_DB_PATH"
ENV_CONTENT_DIR = "AOS_CONTENT_DIR"
ENV_MEMORY_DIR = "AOS_MEMORY_DIR"
ENV_POLICIES_DIR = "AOS_POLICIES_DIR"


def resolve_root() -> Path:
    """Resolve the Agent OS root.

    Priority: ``AGENT_OS_ROOT`` env var, else the repository root inferred
    from this package's location. Never falls back to a user-home install
    directory.
    """
    env = os.environ.get(ENV_ROOT)
    if env:
        return Path(env).expanduser().resolve()

    # config.py lives at <root>/aos/config.py -> parents[1] is <root>.
    root = Path(__file__).resolve().parents[1]
    if (root / "aos" / "__init__.py").is_file():
        return root

    raise ConfigError(
        f"cannot resolve Agent OS root: set {ENV_ROOT} or run from the repo"
    )


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if value:
        return Path(value).expanduser().resolve()
    return default


@dataclass(frozen=True)
class Paths:
    """Resolved filesystem layout for a single Agent OS invocation."""

    root: Path
    store_dir: Path
    db_path: Path
    content_dir: Path
    memory_dir: Path
    policies_dir: Path
    loops_dir: Path
    evidence_dir: Path
    pending_dir: Path

    def ensure_store(self) -> None:
        """Create the runtime store directories if they do not exist."""
        for directory in (
            self.store_dir,
            self.loops_dir,
            self.evidence_dir,
            self.pending_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, str]:
        return {name: str(value) for name, value in self.__dict__.items()}


def get_paths() -> Paths:
    """Resolve all paths fresh from the current environment."""
    root = resolve_root()

    store_dir = _env_path(ENV_STORE_DIR, root / "store")
    content_dir = _env_path(ENV_CONTENT_DIR, root / "content")

    return Paths(
        root=root,
        store_dir=store_dir,
        db_path=_env_path(ENV_DB_PATH, store_dir / "aos.db"),
        content_dir=content_dir,
        memory_dir=_env_path(ENV_MEMORY_DIR, content_dir / "memory"),
        policies_dir=_env_path(ENV_POLICIES_DIR, content_dir / "policies"),
        loops_dir=store_dir / "loops",
        evidence_dir=store_dir / "evidence",
        pending_dir=store_dir / "pending-postflight",
    )


def reset_caches() -> None:
    """Drop every content-layer cache.

    Those modules resolve their paths through this file, so they are imported
    here rather than at module scope. Called around every test, and available
    to a long-lived host that swaps ``AOS_CONTENT_DIR`` mid-process.

    ``routing.router`` and ``adapters.base`` are deliberately not reset: that
    singleton loads package data, and the adapter registry holds built-in
    providers — neither depends on the content directory.
    """
    from aos.core.memory import policy
    from aos.core.routing import taxonomy

    policy.reload()
    taxonomy.reload()


def __getattr__(name: str) -> Paths:
    """Lazily expose ``aos.config.paths`` resolved from the current env."""
    if name == "paths":
        return get_paths()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
