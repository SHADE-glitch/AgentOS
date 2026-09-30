"""Authoring memories by hand — the entry point the store never had.

``MemoryStore.upsert_memory`` existed from the first commit but was only ever
called from tests, so a fresh database could not acquire a memory by any means
the engine offered. With zero memories, recall returns nothing, which leaves
``record_stage`` no ``memories_used`` to build candidates from and
``run_learning`` iterates over an empty group list: every step downstream of
cold start is unobservable, however correct it is. This module is that missing
entry point, and the reason the seed ships real, checkable facts about this
repository.

Length limits are enforced here rather than in SQL: the schema has no CHECK on
``title``/``body``, and a memory that cannot be rendered inside the injection
budget is not useful, so an author should hear about it immediately.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from aos.contract.schema import MEMORY_TYPE
from aos.core.memory.evolve import EVIDENCE_LEVELS
from aos.core.memory.store import MemoryStore

CONFIDENCE_LEVELS = ("low", "medium", "high")

MAX_TITLE_CHARS = 120
MAX_BODY_CHARS = 2000

# The vocabulary the engine writes today. The lifecycle states (superseded,
# invalidated, archived) arrive with the schema phase, and this table with them.
STATUSES = ("active", "candidate", "validated", "degraded", "archived_candidate")


class AuthoringError(ValueError):
    """A memory cannot be stored as written."""


def _normalise(text: str) -> str:
    return " ".join(str(text).split())


def seed_id(title: str, body: str) -> str:
    """A stable id for a seeded memory, so re-seeding is an idempotent upsert.

    Derived from content rather than handed out randomly: the same entry read
    twice must not become two memories. Case and layout are folded away for
    the same reason — "Guard at the boundary" and "guard  at\nthe boundary" are
    one fact, and an id that says otherwise re-introduces the duplicate the
    derived id exists to prevent.
    """
    digest = hashlib.sha1(
        f"{_normalise(title).lower()}|{_normalise(body).lower()}".encode("utf-8")
    )
    return f"M-{digest.hexdigest()[:8].upper()}"


def new_memory(
    *,
    title: str,
    body: str,
    type: str = "pattern",
    category: str = "",
    tags: Iterable[str] = (),
    roles: Iterable[str] = (),
    evidence_level: str = "hypothesis",
    confidence: str = "low",
    status: str = "active",
    source_task: str = "",
    memory_id: str = "",
    verified: bool = False,
) -> dict[str, Any]:
    """Build a storable memory row, or raise :class:`AuthoringError`.

    Without ``verified`` an authored memory is forced down to
    ``evidence_level=hypothesis`` / ``confidence=low``, which is what keeps the
    renderer labelling it ``未验证，仅作提示`` instead of handing an unproven claim
    to the model as established practice.
    """
    title = _normalise(title)
    body = _normalise(body)

    if not title:
        raise AuthoringError("title must not be empty")
    if len(title) > MAX_TITLE_CHARS:
        raise AuthoringError(f"title is {len(title)} chars, the cap is {MAX_TITLE_CHARS}")
    if not body:
        raise AuthoringError("body must not be empty")
    if len(body) > MAX_BODY_CHARS:
        raise AuthoringError(f"body is {len(body)} chars, the cap is {MAX_BODY_CHARS}")
    if type not in MEMORY_TYPE:
        raise AuthoringError(f"type {type!r} is not one of {sorted(MEMORY_TYPE)}")
    if evidence_level not in EVIDENCE_LEVELS:
        raise AuthoringError(
            f"evidence_level {evidence_level!r} is not one of {list(EVIDENCE_LEVELS)}"
        )
    if confidence not in CONFIDENCE_LEVELS:
        raise AuthoringError(f"confidence {confidence!r} is not one of {CONFIDENCE_LEVELS}")
    if status not in STATUSES:
        raise AuthoringError(f"status {status!r} is not one of {STATUSES}")

    if not verified:
        evidence_level, confidence = "hypothesis", "low"

    row: dict[str, Any] = {
        "memory_id": memory_id or seed_id(title, body),
        "type": type,
        "category": _normalise(category).lower(),
        "title": title,
        "body": body,
        "evidence_level": evidence_level,
        "confidence": confidence,
        "status": status,
        "source_task": source_task,
        # Kept on the row so `add` and `seed` normalise them the same way;
        # MemoryStore.upsert_memory takes them as separate arguments.
        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        "roles": [str(role).strip() for role in roles if str(role).strip()],
    }
    return row


def _entries(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [entry for entry in document if isinstance(entry, dict)]
    if isinstance(document, dict):
        memories = document.get("memories")
        if isinstance(memories, list):
            return [entry for entry in memories if isinstance(entry, dict)]
    raise AuthoringError("a seed file must be a list, or an object with a 'memories' list")


def seed_from_dir(
    directory: Path,
    *,
    store: Optional[MemoryStore] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Load ``directory/**/*.json`` into the store without overwriting edits.

    Entries either carry an explicit ``memory_id`` or get a content-derived one,
    and both are stable, so a run is repeatable: an entry already in the
    database is skipped rather than rewritten, which is what stops a re-seed
    from silently reverting a memory a human has since refined.
    """
    owns_store = store is None
    store = store or MemoryStore()
    report: dict[str, Any] = {"seeded": [], "skipped": [], "errors": [], "files": []}
    try:
        if not directory.is_dir():
            report["errors"].append(f"no seed directory at {directory}")
            return report

        for path in sorted(directory.rglob("*.json")):
            report["files"].append(str(path))
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                entries = _entries(document)
            except (OSError, json.JSONDecodeError, AuthoringError) as exc:
                report["errors"].append(f"{path.name}: {exc}")
                continue

            for entry in entries:
                try:
                    row = new_memory(**{k: v for k, v in entry.items() if k != "verified"},
                                     verified=bool(entry.get("verified", False)))
                except (AuthoringError, TypeError) as exc:
                    report["errors"].append(f"{path.name}: {exc}")
                    continue

                memory_id = str(row["memory_id"])
                if not force and store.get_memory(memory_id) is not None:
                    report["skipped"].append(memory_id)
                    continue

                store.upsert_memory(row, tags=row["tags"], roles=row["roles"])
                report["seeded"].append(memory_id)

        return report
    finally:
        if owns_store:
            store.close()
