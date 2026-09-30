"""Config / path resolution tests, including the no-hardcoded-root guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from aos import config
from aos.core.memory import policy
from aos.core.orchestration import orchestrator
from aos.core.routing import taxonomy

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


def test_content_root_change_is_picked_up_without_reload(monkeypatch, tmp_path):
    """Content caches are keyed by resolved path, not by policy name.

    This is the regression guard for cross-invocation leakage: while the key
    was the bare name, the first content root consulted pinned its thresholds
    for the whole process, and correctness depended on every caller
    remembering to call reload().
    """
    root_a = tmp_path / "a"
    (root_a / "policies").mkdir(parents=True)
    (root_a / "routing").mkdir(parents=True)
    (root_a / "policies" / "promotion.json").write_text(
        '{"min_observations": 42}', encoding="utf-8"
    )
    (root_a / "policies" / "orchestration.json").write_text(
        '{"activation_rules": {"domain_threshold": 7}}', encoding="utf-8"
    )
    (root_a / "routing" / "taxonomy-map.json").write_text(
        '{"map": {"bugfix": "root-a-fixer"}}', encoding="utf-8"
    )

    monkeypatch.setenv("AOS_CONTENT_DIR", str(root_a))
    assert policy.load_policy("promotion")["min_observations"] == 42
    assert orchestrator.load_rules()["activation_rules"]["domain_threshold"] == 7
    assert taxonomy.resolve_role("bugfix") == "root-a-fixer"

    # A second root that ships no override files at all, still with no reload().
    root_b = tmp_path / "b"
    (root_b / "policies").mkdir(parents=True)
    monkeypatch.setenv("AOS_CONTENT_DIR", str(root_b))
    assert policy.load_policy("promotion")["min_observations"] == 2
    assert orchestrator.load_rules()["activation_rules"]["domain_threshold"] == 2
    assert taxonomy.resolve_role("bugfix") == "code-reviewer"


def test_reset_caches_clears_every_content_cache(monkeypatch, tmp_path):
    """``reset_caches`` must cover all three content-cached loaders."""
    policies = tmp_path / "policies"
    routing = tmp_path / "routing"
    policies.mkdir(parents=True)
    routing.mkdir(parents=True)
    (policies / "promotion.json").write_text('{"min_observations": 99}', encoding="utf-8")
    (policies / "orchestration.json").write_text(
        '{"activation_rules": {"domain_threshold": 9}}', encoding="utf-8"
    )
    (routing / "taxonomy-map.json").write_text('{"map": {"bugfix": "cached"}}', encoding="utf-8")
    monkeypatch.setenv("AOS_CONTENT_DIR", str(tmp_path))

    # Populate all three caches, then empty the directory they read from.
    assert policy.load_policy("promotion")["min_observations"] == 99
    assert orchestrator.load_rules()["activation_rules"]["domain_threshold"] == 9
    assert taxonomy.resolve_role("bugfix") == "cached"
    for path in list(policies.glob("*.json")) + list(routing.glob("*.json")):
        path.unlink()

    config.reset_caches()
    assert policy.load_policy("promotion")["min_observations"] == 2
    assert orchestrator.load_rules()["activation_rules"]["domain_threshold"] == 2
    assert taxonomy.resolve_role("bugfix") == "code-reviewer"


def test_engine_has_no_hardcoded_install_root():
    """The engine must never hardcode an install location."""
    engine = REPO_ROOT / "aos"
    offenders = []
    for path in engine.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "/home/shade/.agents" in text or "~/.agents" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"hardcoded install root in: {offenders}"
