"""Task routing: classify a task and select a lead skill + concrete role."""

from aos.core.routing.decision import ClassificationResult, DecisionContext
from aos.core.routing.router import HybridRouter, get_hybrid_router, reset, route_task
from aos.core.routing.taxonomy import known_roles, resolve_role, resolve_roles

__all__ = [
    "DecisionContext",
    "ClassificationResult",
    "HybridRouter",
    "get_hybrid_router",
    "reset",
    "route_task",
    "resolve_role",
    "resolve_roles",
    "known_roles",
]
