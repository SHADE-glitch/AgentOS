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

from aos.contract.schema import (
    MEMORY_LIFECYCLE,
    MEMORY_SCOPE_EXACT,
    MEMORY_SCOPE_PREFIXES,
    MEMORY_TYPE,
)
from aos.core.memory.evolve import EVIDENCE_LEVELS
from aos.core.memory.store import MemoryStore, _now as _timestamp

CONFIDENCE_LEVELS = ("low", "medium", "high")

MAX_TITLE_CHARS = 120
MAX_BODY_CHARS = 2000

# The lifecycle and type vocabularies come from the contract, not a local copy:
# a host reading `memory.memories[].type` must be able to switch on the same set
# the store enforces, or the two drift and one of them starts lying.
STATUSES = tuple(sorted(MEMORY_LIFECYCLE))
TYPES = tuple(sorted(MEMORY_TYPE))


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


def validate_scope(scope: str) -> str:
    """Check ``global`` / ``project:<id>`` / ``session:<id>`` and return it.

    The two halves are checked separately on purpose: a bare ``project:`` with no
    id looks like a scope and is not one, and a store full of those would be
    filtered by nothing and shown everywhere.
    """
    scope = _normalise(scope)
    if scope in MEMORY_SCOPE_EXACT:
        return scope
    for prefix in MEMORY_SCOPE_PREFIXES:
        if scope.startswith(prefix) and scope[len(prefix):].strip():
            return scope
    raise AuthoringError(
        f"scope {scope!r} must be 'global', 'project:<id>' or 'session:<id>'"
    )


def new_memory(
    *,
    title: str,
    body: str,
    type: str = "episodic",
    category: str = "",
    tags: Iterable[str] = (),
    roles: Iterable[str] = (),
    evidence_level: str = "hypothesis",
    confidence: str = "low",
    status: Optional[str] = None,
    scope: str = "global",
    when_to_apply: str = "",
    revalidate_after: str = "",
    source_task: str = "",
    source_project: str = "",
    source_session: str = "",
    source_loop_id: str = "",
    memory_id: str = "",
    verified: bool = False,
) -> dict[str, Any]:
    """Build a storable memory row, or raise :class:`AuthoringError`.

    ``verified`` is the gate on birth state, and it is not a label the caller
    can fake its way past: without it the memory is forced to
    ``evidence_level=hypothesis``, ``lane=hypothesis``, ``status=candidate``,
    which is what keeps the renderer marking it ``未验证，仅作提示`` instead of
    handing an unproven claim to the model as established practice. Reaching
    ``active`` or ``verified`` is the promotion path's job, not the author's.
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
        raise AuthoringError(f"type {type!r} is not one of {TYPES}")
    if evidence_level not in EVIDENCE_LEVELS:
        raise AuthoringError(
            f"evidence_level {evidence_level!r} is not one of {list(EVIDENCE_LEVELS)}"
        )
    if confidence not in CONFIDENCE_LEVELS:
        raise AuthoringError(f"confidence {confidence!r} is not one of {CONFIDENCE_LEVELS}")
    scope = validate_scope(scope)

    if status is not None and status not in MEMORY_LIFECYCLE:
        # Rejected even though an unverified memory is about to be forced to
        # `candidate` anyway: storing something else in silence would tell the
        # caller their state was accepted when it was not.
        raise AuthoringError(f"status {status!r} is not one of {STATUSES}")

    if verified:
        lane = "hypothesis" if evidence_level == "hypothesis" else "standard"
        resolved_status = status or "active"
        last_verified_at = _timestamp()
    else:
        evidence_level, confidence = "hypothesis", "low"
        lane = "hypothesis"
        resolved_status = "candidate"
        last_verified_at = ""

    row: dict[str, Any] = {
        "memory_id": memory_id or seed_id(title, body),
        "type": type,
        "category": _normalise(category).lower(),
        "title": title,
        "body": body,
        "evidence_level": evidence_level,
        "confidence": confidence,
        "status": resolved_status,
        "lane": lane,
        "scope": scope,
        "when_to_apply": _normalise(when_to_apply),
        "revalidate_after": _normalise(revalidate_after),
        "last_verified_at": last_verified_at,
        "source_task": source_task,
        "source_project": source_project,
        "source_session": source_session,
        "source_loop_id": source_loop_id,
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
