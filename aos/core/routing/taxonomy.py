"""Taxonomy resolution: abstract router skill id -> concrete agent role.

The router emits canonical *abstract* skill ids (``bugfix``, ``performance``,
...). Downstream consumers (role resolution, recall filtering) need a
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


@lru_cache(maxsize=64)
def _read_json(path: Path) -> dict:
    """Read a registry or content JSON file, memoised by its resolved path.

    Every caller treats the result as read-only, so sharing one parsed object
    per path is safe; a file rewritten in place needs :func:`reload`.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _content_map_path() -> Path:
    return get_paths().content_dir / "routing" / "taxonomy-map.json"


def _content_roles_path() -> Path:
    return get_paths().content_dir / "routing" / "roles.json"


def _role_entries(path: Path) -> dict[str, dict]:
    entries = _read_json(path).get("roles", [])
    return {
        entry["id"]: entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
    }


def role_catalog() -> dict[str, dict]:
    """Return the effective role catalog ``{role_id: entry}``.

    Content-layer entries are merged over the built-in catalog, so a project
    can add roles or refine ``domain``/``dependencies`` without forking the
    engine.
    """
    catalog = _role_entries(_DEFAULT_ROLES_PATH)
    catalog.update(_role_entries(_content_roles_path()))
    return catalog


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
    return list(role_catalog())


def reload() -> None:
    """Clear the parsed-JSON caches (needed when a file is rewritten in place)."""
    _read_json.cache_clear()
