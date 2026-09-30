"""Rule-based conflict detection between memories.

No models, no embeddings — a small, deterministic keyword rule set ported
from the old ``conflict_detector.py``. A detected conflict never rejects a
memory outright; it only forces the promotion through the human review gate,
so a false positive costs a review, not correctness.
"""

from __future__ import annotations

from typing import Any, Iterable

# Pairs of mutually opposed concepts. If one side appears in one memory's
# tags/text and the other side appears in another's, they are flagged.
CONTRADICTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "isolation": ("shared", "multi-tenant"),
    "single": ("multi", "distributed"),
    "centralized": ("decentralized", "distributed"),
    "synchronous": ("asynchronous", "async"),
    "strong-consistency": ("eventual-consistency",),
    "monolith": ("microservice",),
    "single-database": ("multi-database",),
    "lock": ("lock-free", "optimistic"),
    "scale-up": ("scale-out",),
    "tight-coupling": ("loose-coupling",),
    "security": ("convenience",),
    "performance": ("correctness",),
}

# Only strong opposites count as a polarity conflict.
POLARITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "positive": ("recommend", "best", "optimal", "effective"),
    "negative": ("avoid", "reject", "anti-pattern", "harmful"),
}


def _tags(memory: dict[str, Any]) -> set[str]:
    return {str(t).lower() for t in memory.get("tags", [])}


def _text(memory: dict[str, Any]) -> str:
    return f"{memory.get('title', '')} {memory.get('body', '')}".lower()


def detect_tag_conflicts(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Conflicts where one memory's tag opposes another's."""
    tags_a, tags_b = _tags(a), _tags(b)
    conflicts: list[str] = []
    for concept, opposites in CONTRADICTION_KEYWORDS.items():
        if concept in tags_a:
            conflicts += [f"tag:{concept}<->{o}" for o in opposites if o in tags_b]
        if concept in tags_b:
            conflicts += [f"tag:{o}<->{concept}" for o in opposites if o in tags_a]
    return conflicts


def detect_polarity_conflicts(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Conflicts where one memory recommends what the other rejects."""
    tags_a, tags_b = _tags(a), _tags(b)
    conflicts: list[str] = []
    for positive in POLARITY_KEYWORDS["positive"]:
        for negative in POLARITY_KEYWORDS["negative"]:
            if positive in tags_a and negative in tags_b:
                conflicts.append(f"polarity:{positive}<->{negative}")
            if negative in tags_a and positive in tags_b:
                conflicts.append(f"polarity:{negative}<->{positive}")
    return conflicts


def detect_text_conflicts(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Conflicts where opposed concepts appear in the memory text."""
    text_a, text_b = _text(a), _text(b)
    conflicts: list[str] = []
    for concept, opposites in CONTRADICTION_KEYWORDS.items():
        if concept in text_a:
            conflicts += [f"text:{concept}<->{o}" for o in opposites if o in text_b]
        if concept in text_b:
            conflicts += [f"text:{o}<->{concept}" for o in opposites if o in text_a]
    return conflicts


def detect_conflicts(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """All conflict reasons between two memories (deduplicated, sorted)."""
    reasons = set(detect_tag_conflicts(a, b))
    reasons.update(detect_polarity_conflicts(a, b))
    reasons.update(detect_text_conflicts(a, b))
    return sorted(reasons)


def find_conflicts(memories: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every conflicting pair among *memories*."""
    items = [m for m in memories if m.get("memory_id")]
    found: list[dict[str, Any]] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            reasons = detect_conflicts(a, b)
            if reasons:
                found.append(
                    {
                        "memory_a": a["memory_id"],
                        "memory_b": b["memory_id"],
                        "reasons": reasons,
                    }
                )
    return found


def conflicting_ids(conflicts: Iterable[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for conflict in conflicts:
        ids.add(conflict["memory_a"])
        ids.add(conflict["memory_b"])
    return ids


def index_by_id(pairs: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group conflict pairs by each memory they involve.

    Exists so one learning cycle can compute the pairwise scan *once*. Calling
    :func:`conflicts_for` per memory re-scans every pair for every group, which is
    cubic in the size of the store — the same scan, done n times over.
    """
    indexed: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        for side in ("memory_a", "memory_b"):
            indexed.setdefault(pair[side], []).append(pair)
    return indexed


def conflicts_for(memory_id: str, memories: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conflicts that involve *memory_id*."""
    return [c for c in find_conflicts(memories) if memory_id in (c["memory_a"], c["memory_b"])]


def has_conflict(memory_id: str, memories: Iterable[dict[str, Any]]) -> bool:
    return bool(conflicts_for(memory_id, memories))
