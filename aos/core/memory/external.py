"""Read-only recall over basic-memory notes — a pointer, never a second memory store.

basic-memory owns these markdown notes and their truth. The engine borrows one thing
from it: *that a note exists about this subject*, as a title plus a permalink the
model can go read. So three rules hold this apart from the memory table:

* the neighbour's SQLite index is opened ``mode=ro`` with ``query_only`` on; nothing
  here may write, and `tests/test_external.py` asserts that against the source and
  against the file's bytes;
* every row is labelled ``evidence_level=external`` with an **empty** confidence —
  no human gate ever looked at a note, so claiming a level for it would be invented
  provenance, and rendering it as `事实`/`不要` would dress a note up as a verdict;
* any failure is silence, not a degraded preflight. A missing, locked, migrated or
  reshaped neighbour database means "nothing external this time", never a run that
  stops because a neighbour was unavailable.

The CLI is deliberately not used: `bm` answers in 8.5-9.2 s and a preflight budget is
1200 ms, while the read-only index answers a full scan of 52 notes in well under a
millisecond. Retrieval stays in-process and deterministic.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from aos.config import basic_memory_db
from aos.core.memory.policy import load_policy

# A title or tag token is a name of something: latin words, digits, and CJK runs.
# Splitting on everything else keeps `会话总结-GNOME系统运维精华` into two tokens
# instead of losing the whole title to one unmatchable blob.
_TOKEN = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]+")


def _open_ro(path: Path) -> Optional[sqlite3.Connection]:
    """A handle that cannot write, or `None` — the file may not exist at all."""
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2)
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        conn.close()
        return None
    return conn


def _tags_of(entity_metadata: Any) -> list[str]:
    """Frontmatter tags, or nothing. basic-memory stores them as JSON, occasionally badly."""
    if isinstance(entity_metadata, (bytes, bytearray)):
        entity_metadata = entity_metadata.decode("utf-8", errors="replace")
    try:
        payload = json.loads(entity_metadata or "{}")
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    tags = payload.get("tags")
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",")]
    if not isinstance(tags, list):
        return []
    return [str(tag).strip() for tag in tags if str(tag).strip()]


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text or "")]


def _squashed(text: str) -> str:
    """The same text with every separator removed.

    Without this, a note tagged `spring-boot` is unreachable from the phrase
    "Spring Boot" — and pointers that only match how somebody happened to type a
    name are not measuring relevance, they are measuring punctuation.
    """
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


def _in(needle: str, squashed: str, value: str) -> bool:
    value = value.lower()
    return value in needle or _squashed(value) in squashed


def _score(query: str, squashed: str, title: str, tags: list[str], min_tag_overlap: int) -> int:
    """Tag overlap is worth twice a title overlap; both are literal substring tests.

    Literal, on purpose: the alternative is a similarity that cannot be explained at
    review time. This number decides whether a pointer appears, never whether a
    lesson is true — those are different authorities and only one of them is ours.
    """
    overlap = sum(1 for tag in tags if _in(query, squashed, tag))
    hits = sum(1 for token in set(_tokens(title)) if _in(query, squashed, token))
    if overlap < min_tag_overlap and not hits:
        return 0
    return 2 * overlap + hits


def recall(query: str, *, k: Optional[int] = None, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Top-``k`` basic-memory notes matching ``query``, as labelled pointers."""
    rules = load_policy("external")
    if not rules.get("enabled", True) or not (query or "").strip():
        return []

    limit = int(k if k is not None else rules.get("max_items", 2))
    limit = max(0, min(limit, int(rules.get("max_items", 2))))
    if limit == 0:
        return []

    needle = " ".join(str(query).lower().split())
    squashed = _squashed(needle)
    body_limit = int(rules.get("max_body_chars", 0))
    wanted = "markdown_content" if body_limit > 0 else "''"

    try:
        conn = _open_ro(db_path or basic_memory_db())
    except (sqlite3.Error, OSError):
        # `_open_ro` swallows what it can; this is the rest — a path that turned out
        # to be a directory, a filesystem that refuses us. Fail-open means the
        # neighbour is never able to stop a preflight, by any route.
        return []
    if conn is None:
        return []
    try:
        rows = conn.execute(
            f"SELECT e.title, e.permalink, e.file_path, e.entity_metadata, {wanted} "
            "FROM entity e LEFT JOIN note_content n ON n.entity_id = e.id "
            "ORDER BY e.permalink"
        ).fetchall()
    except sqlite3.Error:
        # A migrated or half-written index is absence, not a failed run.
        return []
    finally:
        conn.close()

    min_tag_overlap = int(rules.get("min_tag_overlap", 1))
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for title, permalink, file_path, metadata, markdown in rows:
        identifier = str(permalink or title or "").strip()
        if not identifier:
            continue
        tags = _tags_of(metadata)
        score = _score(needle, squashed, str(title or ""), tags, min_tag_overlap)
        if score <= 0:
            continue
        scored.append((
            score,
            identifier,
            {
                "memory_id": f"bm:{identifier}",
                "type": "note",
                "title": str(title or identifier),
                # A body only exists if the policy asked for one; by default the
                # note's content stays in the note.
                "body": (str(markdown or "") if body_limit > 0 else ""),
                "when_to_apply": "",
                "evidence_level": "external",
                "confidence": "",
                "lane": "external",
                "is_hypothesis": False,
                "external": True,
                "source": "basic-memory",
                "permalink": identifier,
                "path": str(file_path or ""),
                "tags": tags,
                "final_score": float(score),
                "status": "",
                "scope": "global",
                "source_task": "",
                "source_project": "",
                "source_loop_id": "",
                "created_at": "",
                "last_verified_at": "",
                "revalidate_after": "",
                "version": 1,
            },
        ))

    # Score first, permalink last: the same query against the same index must
    # produce the same block, or "deterministic retrieval" is a claim with nothing
    # behind it.
    scored.sort(key=lambda item: (-item[0], item[1]))
    picked: dict[str, dict[str, Any]] = {}
    for points, identifier, row in scored:
        picked.setdefault(str(row["memory_id"]), row)
        if len(picked) >= limit:
            break
    return list(picked.values())
