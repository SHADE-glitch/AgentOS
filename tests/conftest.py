"""Shared pytest fixtures.

Every test runs hermetically: the engine root points at the repository, and
all mutable state goes to a per-test temporary directory so tests never
touch the real ``store/`` and can run in parallel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aos.config import reset_caches  # noqa: E402  (needs the path hook above)


@pytest.fixture(autouse=True)
def hermetic_env(tmp_path, monkeypatch):
    """Point the engine at a throwaway store/content for every test."""
    store = tmp_path / "store"
    content = tmp_path / "content"
    monkeypatch.setenv("AGENT_OS_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("AOS_STORE_DIR", str(store))
    monkeypatch.setenv("AOS_DB_PATH", str(store / "aos.db"))
    monkeypatch.setenv("AOS_CONTENT_DIR", str(content))
    # The neighbour database is never read by accident: a test that wants it sets
    # AOS_BM_DB to a fixture of its own. Left alone, this points at a path that
    # does not exist, which is also the production default's failure mode.
    monkeypatch.setenv("AOS_BM_DB", str(tmp_path / "no-basic-memory" / "memory.db"))
    # Publishing an approved lesson reaches outside the repository, so both ends of
    # it are disconnected here: the command does not exist, and the neighbour's
    # config directory — the only way to find its vault — does not either. A test
    # that wants to publish points one or both of them at a fixture of its own.
    monkeypatch.setenv("AOS_BM_BIN", str(tmp_path / "no-basic-memory" / "basic-memory"))
    monkeypatch.setenv("AOS_BM_CONFIG_DIR", str(tmp_path / "no-basic-memory"))
    reset_caches()
    yield
    reset_caches()
