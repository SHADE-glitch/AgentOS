"""Config / path resolution tests, including the no-hardcoded-root guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from aos import config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_resolve_root_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_OS_ROOT", str(tmp_path))
    assert config.resolve_root() == tmp_path.resolve()


def test_resolve_root_defaults_to_repo(monkeypatch):
    monkeypatch.delenv("AGENT_OS_ROOT", raising=False)
    assert config.resolve_root() == REPO_ROOT


def test_paths_are_derived_from_root(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_OS_ROOT", str(tmp_path))
    monkeypatch.delenv("AOS_STORE_DIR", raising=False)
    monkeypatch.delenv("AOS_DB_PATH", raising=False)
    monkeypatch.delenv("AOS_CONTENT_DIR", raising=False)
    paths = config.get_paths()

    assert paths.root == tmp_path.resolve()
    assert paths.store_dir == tmp_path.resolve() / "store"
    assert paths.db_path == paths.store_dir / "aos.db"
    assert paths.content_dir == tmp_path.resolve() / "content"
    assert paths.loops_dir == paths.store_dir / "loops"
    assert paths.evidence_dir == paths.store_dir / "evidence"


def test_store_paths_are_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("AOS_STORE_DIR", str(tmp_path / "custom-store"))
    monkeypatch.delenv("AOS_DB_PATH", raising=False)
    paths = config.get_paths()
    assert paths.store_dir == (tmp_path / "custom-store").resolve()
    assert paths.db_path == paths.store_dir / "aos.db"


def test_lazy_paths_attribute(monkeypatch, tmp_path):
    monkeypatch.setenv("AOS_STORE_DIR", str(tmp_path / "lazy"))
    assert config.paths.store_dir == (tmp_path / "lazy").resolve()


def test_ensure_store_creates_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("AOS_STORE_DIR", str(tmp_path / "store"))
    paths = config.get_paths()
    paths.ensure_store()
    assert paths.loops_dir.is_dir()
    assert paths.evidence_dir.is_dir()
    assert paths.pending_dir.is_dir()


def test_engine_has_no_hardcoded_install_root():
    """The engine must never hardcode an install location."""
    engine = REPO_ROOT / "aos"
    offenders = []
    for path in engine.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "/home/shade/.agents" in text or "~/.agents" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"hardcoded install root in: {offenders}"
