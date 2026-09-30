"""Taxonomy resolution: abstract router skill id -> concrete agent role.

The router emits canonical *abstract* skill ids (``bugfix``, ``performance``,
...). Downstream consumers (role/skill loading, orchestration) need a
concrete *role* (``code-reviewer``, ``frontend-performance``, ...). This module
is the single place that maps between the two, fixing the vocabulary mismatch
that previously broke the runtime chain.

Resolution order:
  1. the engine's built-in map (``registry/taxonomy-map.json``)
  2. an optional content-layer override (``content/routing/taxonomy-map.json``)

When a mapping is absent, ``resolve_role`` returns ``None`` and the router
still works — role loading simply degrades.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from aos.config import get_paths

_REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
_DEFAULT_MAP_PATH = _REGISTRY_DIR / "taxonomy-map.json"
_DEFAULT_ROLES_PATH = _REGISTRY_DIR / "roles.json"


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=None)
def _content_map_path() -> Path:
    return get_paths().content_dir / "routing" / "taxonomy-map.json"


def taxonomy_map() -> dict[str, str]:
    """Return the effective abstract-id -> role map (content overrides built-in)."""
    mapping = dict(_read_json(_DEFAULT_MAP_PATH).get("map", {}))
    override = _read_json(_content_map_path()).get("map")
    if isinstance(override, dict):
        mapping.update({str(k): str(v) for k, v in override.items()})
    return mapping


def resolve_role(abstract_id: Optional[str]) -> Optional[str]:
    """Resolve a single abstract skill id to a concrete role, or None."""
    if not abstract_id or abstract_id == "fallback":
        return None
    return taxonomy_map().get(abstract_id)


def resolve_roles(abstract_ids: list[str]) -> list[str]:
    """Resolve a list of abstract ids, dropping any that cannot be mapped."""
    roles = []
    for skill_id in abstract_ids:
        role = resolve_role(skill_id)
        if role and role not in roles:
            roles.append(role)
    return roles


def known_roles() -> list[str]:
    """Return the built-in role catalog (ids only)."""
    roles = _read_json(_DEFAULT_ROLES_PATH).get("roles", [])
    return [r["id"] for r in roles if isinstance(r, dict) and "id" in r]


def reload() -> None:
    """Clear caches so a changed content override is picked up."""
    _content_map_path.cache_clear()
