"""Routing tests: classification, taxonomy resolution and port fidelity."""

from __future__ import annotations

import json
from pathlib import Path

from aos.config import get_paths
from aos.core.routing import router as router_mod
from aos.core.routing import taxonomy
from aos.core.routing.router import HybridRouter, route_task

REGISTRY = Path(__file__).resolve().parents[1] / "aos" / "core" / "routing" / "registry"
ABSTRACT_IDS = {
    "bugfix",
    "refactor",
    "performance",
    "security",
    "data_model",
    "test",
    "observability",
    "config",
    "infra",
    "report",
}


def test_registry_is_bundled_not_external():
    r = HybridRouter()
    assert REGISTRY in r.registry_path.parents


def test_route_bugfix():
    decision = route_task("fix the null pointer crash")
    assert decision["selected"] == "bugfix"
    assert decision["lead_role"] == "code-reviewer"


def test_route_test_task():
    decision = route_task("write a unit test for the assertion and mock the fixture")
    assert decision["selected"] == "test"


def test_route_returns_roles():
    decision = route_task("fix the null pointer crash")
    assert decision["lead_role"] == "code-reviewer"
    assert isinstance(decision["support_roles"], list)


def test_unknown_domain_escalates():
    decision = route_task("I want the dashboard to auto-curate a cocoa distillation schedule")
    assert decision["route_mode"] == "planner"


def test_genuine_ambiguity_falls_back():
    decision = route_task("the intent is genuinely ambiguous, low confidence")
    assert decision["selected"] == "fallback"


def test_every_abstract_id_maps_to_a_role():
    mapping = taxonomy.taxonomy_map()
    for skill_id in ABSTRACT_IDS:
        assert mapping.get(skill_id), f"{skill_id} has no role mapping"


def test_mapped_roles_are_known():
    roles = set(taxonomy.known_roles())
    unknown = [role for role in taxonomy.taxonomy_map().values() if role not in roles]
    assert unknown == [], f"taxonomy maps to unknown roles: {unknown}"


def test_resolve_role_handles_fallback_and_unknown():
    assert taxonomy.resolve_role("fallback") is None
    assert taxonomy.resolve_role("") is None
    assert taxonomy.resolve_role("no-such-skill") is None


def test_content_layer_overrides_taxonomy():
    routing_dir = get_paths().content_dir / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)
    (routing_dir / "taxonomy-map.json").write_text(
        json.dumps({"map": {"bugfix": "my-fixer"}}), encoding="utf-8"
    )
    taxonomy.reload()
    try:
        assert taxonomy.resolve_role("bugfix") == "my-fixer"
        # Unlisted ids still fall back to the built-in map.
        assert taxonomy.resolve_role("security") == "security-engineer"
    finally:
        taxonomy.reload()


def test_router_reset_reloads_registry():
    first = router_mod.get_hybrid_router()
    router_mod.reset()
    second = router_mod.get_hybrid_router()
    assert first is not second
