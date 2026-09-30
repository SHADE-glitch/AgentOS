"""Read-only backfill: give the loop a past without inventing one.

Two rules shape this module, and both come from the research record
(`docs/research/adoption-records/R-007-history-backfill-rules.md`):

**The source is checked before anything is cleared.** A `--full` that truncates
first and then discovers the database moved or does not exist destroys the index
it was meant to rebuild. Order is the whole protection here, so it is asserted by
a test rather than trusted.

**A composite watermark, not a timestamp.** opencode writes many `part` rows inside
one millisecond, so `WHERE time > mark` silently skips the siblings of the row that
advanced the mark. The mark is therefore `(time, id)` and the comparison is
lexicographic on that pair.

What it may read is a whitelist of columns and JSON paths, all of them structural:
part *types*, a tool part's `state.status` enum, todo *statuses*, counts. What it may
never read is anything carrying a person's words — session titles and slugs, part
text, tool input/output/error bodies, todo contents. Those are not "skipped for
now": they are outside the whitelist, and a shape change in the source degrades to
"this evidence is unavailable" instead of a guess. That is how a probe ends up
firing on nothing forever (okdk read `part.error` where opencode has
`part.state.status`), and here it would be reading somebody's conversation.

Nothing is concluded here. A backfilled session yields linkage and hard signals;
`outcome` stays `partial` with `needs_review = 1`, which means "unknown" to the
learning path — and `source='backfill'` keeps it out of the human queue, because a
person cannot be asked to judge a run nobody observed.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

ENV_BACKFILL_DB = "AOS_BACKFILL_DB"
WATERMARK_KEY = "opencode-sessions"

# Columns and JSON paths this module is allowed to read. Anything not listed is not
# read even if it exists — including the fields that hold text.
SESSION_COLUMNS = ("id", "project_id", "directory", "time_updated", "agent", "model")
PART_PATHS = {
    "type": "$.type",
    "tool_status": "$.state.status",
}
TODO_COLUMNS = ("session_id", "status")

# A tool part is only counted, never copied: `status` is an enum, its siblings
# (`input`, `output`, `error`, `metadata`, `title`) carry conversation content.
_ERROR_STATUSES = {"error"}
_OPEN_TODO_STATUSES = {"pending", "in_progress"}


class BackfillError(RuntimeError):
    """A reason not to read anything. Always raised before any write happens."""


@dataclass
class SessionEvidence:
    """What one historical session can support: hard signals, no verdict."""

    session_id: str
    project: str
    time_updated: int
    agent: str = ""
    model: str = ""
    tool_calls: int = 0
    tool_errors: int = 0
    patches: int = 0
    file_edits: int = 0
    todos_total: int = 0
    todos_open: int = 0
    parts_total: int = 0
    parts_unreadable: bool = False
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        payload = "|".join(
            [
                self.session_id,
                str(self.tool_calls),
                str(self.tool_errors),
                str(self.patches),
                str(self.file_edits),
                str(self.todos_total),
                str(self.todos_open),
                str(self.parts_total),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    def signals(self) -> dict[str, Any]:
        """The snapshot stored beside the observation: counts and enums only.

        A count that could not be read is left out rather than written as `0`, so
        the synthesiser sees lower coverage instead of a clean bill of health
        nobody earned.
        """
        signals: dict[str, Any] = {
            "files_changed": self.file_edits,
            "diff": self.patches,
            "todos_unfinished": self.todos_open,
            "project": self.project,
            "agent": self.agent,
            "model": self.model,
            "origin": "backfill",
        }
        if not self.parts_unreadable:
            signals["tool_errors"] = self.tool_errors
            signals["diff"] = self.patches
        else:
            signals["parts_unreadable"] = True
        return signals

    @property
    def has_evidence(self) -> bool:
        """Skip the empty ones: 199 sessions of which most teach nothing.

        A session with no tool activity and no todo state is a conversation we read
        nothing about, and storing it as an "observation" would be padding the very
        table whose growth the audit called out.
        """
        return bool(
            self.tool_errors
            or self.tool_calls
            or self.patches
            or self.todos_total
            or self.parts_unreadable
        )


def source_path(explicit: str = "") -> Optional[Path]:
    """Where to read from, or None when backfill is off.

    `Path("")` would become `PosixPath('.')` and then look like a real, wrong
    answer, so "not configured" is represented by None rather than an empty path.
    """
    configured = (explicit or os.environ.get(ENV_BACKFILL_DB) or "").strip()
    return Path(configured).expanduser() if configured else None


def open_read_only(path: Optional[Path]) -> sqlite3.Connection:
    """`mode=ro`, and never `immutable=1`.

    The source database is being written by a running opencode and keeps a WAL;
    opening it immutable would let us read a stale snapshot without the write-ahead
    log, which is a silently wrong answer rather than an error.
    """
    if path is None or not path.is_file():
        raise BackfillError(
            f"source database not found: {path or '(unset — set ' + ENV_BACKFILL_DB + ')'}"
        )
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        raise BackfillError(f"source database unreadable: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def probe(conn: sqlite3.Connection) -> dict[str, Any]:
    """What the source can actually tell us, before anything is written.

    A missing table or column is reported as unavailable rather than assumed: an
    older or renamed opencode must degrade to "no evidence", not to a guess about
    where the field moved to.
    """
    tables = _tables(conn)
    report: dict[str, Any] = {"available": {}, "missing": [], "columns": {}}
    for table, wanted in (
        ("session", SESSION_COLUMNS),
        ("part", ("session_id", "data")),
        ("todo", TODO_COLUMNS),
    ):
        if table not in tables:
            report["missing"].append(table)
            continue
        present = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
        report["columns"][table] = sorted(present)
        if table == "session" and "model" in present:
            # `model` is a JSON object in current opencode; the whitelist wants its
            # id, so the probe records whether that extraction is even possible.
            report["available"]["model_id"] = bool(
                conn.execute("SELECT json_valid(model) FROM session LIMIT 1").fetchone()[0]
                if present
                else False
            )
        if wanted:
            absent = [column for column in wanted if column not in present]
            report["missing"].extend(f"{table}.{column}" for column in absent)
    report["available"]["sessions"] = "session" in tables and not any(
        item.startswith("session.") for item in report["missing"]
    )
    report["available"]["parts"] = "part" in tables
    report["available"]["todos"] = "todo" in tables and not any(
        item.startswith("todo.") for item in report["missing"]
    )
    return report


def _json(conn: sqlite3.Connection, path: str) -> str:
    """A json_extract expression, or NULL when the source has no JSON1.

    Reporting "unavailable" instead of failing the whole read: SQLite builds
    without JSON support exist, and the caller then simply has no tool-type data.
    """
    try:
        conn.execute(f"SELECT json_extract('{{}}', '{path}')").fetchone()
    except sqlite3.Error:
        return "NULL"
    return f"json_extract(data, '{path}')"


def iter_sessions(conn: sqlite3.Connection, *, since_time: int, since_id: str, limit: int = 0) -> Iterator[tuple[dict[str, Any], SessionEvidence]]:
    """Sessions after the watermark, ordered by the composite key.

    `> (time, id)` and not `> time`: rows sharing the winning timestamp would
    otherwise be skipped on the next pass, forever, and the skipped rows are the
    interesting ones — they are the ones that arrived at the same instant as the
    run that moved the mark.
    """
    params = {"time": since_time, "id": since_id}
    order = "ORDER BY time_updated, id"
    query = f"""
        SELECT id, project_id, directory, time_updated, agent,
               COALESCE(json_extract(model, '$.id'), model) AS model
        FROM session
        WHERE (time_updated > :time) OR (time_updated = :time AND id > :id)
        {order}
    """
    if limit:
        params["limit"] = limit
        query += " LIMIT :limit"
    try:
        rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        # No JSON1, or a source whose `model` column is not where we think it is:
        # read the plain value rather than failing the pass.
        rows = conn.execute(
            """
            SELECT id, project_id, directory, time_updated, agent, model FROM session
            WHERE (time_updated > :time) OR (time_updated = :time AND id > :id)
            ORDER BY time_updated, id
            """,
            params,
        ).fetchall()
    for row in rows:
        evidence = _evidence_for(conn, row)
        yield dict(row), evidence


def _evidence_for(conn: sqlite3.Connection, session: sqlite3.Row) -> SessionEvidence:
    directory = str(session["directory"] or "")
    evidence = SessionEvidence(
        session_id=str(session["id"]),
        project=os.path.basename(directory.rstrip("/")) if directory else "",
        time_updated=int(session["time_updated"] or 0),
        agent=str(session["agent"] or ""),
        model=str(session["model"] or ""),
    )

    type_expr = _json(conn, PART_PATHS["type"])
    status_expr = _json(conn, PART_PATHS["tool_status"])
    if type_expr != "NULL":
        try:
            rows = conn.execute(
                f"""
                SELECT {type_expr} AS kind, {status_expr} AS status
                FROM part WHERE session_id = :sid
                """,
                {"sid": evidence.session_id},
            ).fetchall()
        except sqlite3.Error:
            # Malformed JSON in a single row fails the whole SELECT in SQLite, and
            # there is no TRY() to fall back on. Losing this session's parts is
            # honest; losing the pass, or reading the blob into Python to parse it
            # row by row, is not: the point of extracting inside the database is
            # that the text fields never leave it.
            evidence.parts_unreadable = True
            rows = []
        for row in rows:
            evidence.parts_total += 1
            kind = row["kind"]
            if kind == "tool":
                evidence.tool_calls += 1
                if str(row["status"] or "") in _ERROR_STATUSES:
                    evidence.tool_errors += 1
            elif kind == "patch":
                evidence.patches += 1

    if _has_table(conn, "todo"):
        counts = conn.execute(
            "SELECT status, COUNT(*) AS n FROM todo WHERE session_id = ? GROUP BY status",
            (evidence.session_id,),
        ).fetchall()
        for row in counts:
            evidence.todos_total += int(row["n"])
            if str(row["status"]) in _OPEN_TODO_STATUSES:
                evidence.todos_open += int(row["n"])

    return evidence


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return name in _tables(conn)


def plan(*, db_path: str = "") -> dict[str, Any]:
    """What a backfill would do, without writing anything."""
    path = source_path(db_path)
    if path is None:
        return {"enabled": False, "reason": f"{ENV_BACKFILL_DB} is not set; nothing is read"}
    conn = open_read_only(path)
    try:
        report = probe(conn)
        totals = conn.execute("SELECT COUNT(*) AS n FROM session").fetchone()["n"] if report["available"]["sessions"] else 0
        return {
            "enabled": True,
            "source": str(path),
            "probe": report,
            "sessions_total": int(totals),
            "with_evidence": _count_evidence(conn, report),
        }
    finally:
        conn.close()


def _count_evidence(conn: sqlite3.Connection, report: dict[str, Any]) -> int:
    if not report["available"]["sessions"]:
        return 0
    total = 0
    for _row, evidence in iter_sessions(conn, since_time=0, since_id=""):
        if evidence.has_evidence:
            total += 1
    return total


def run(
    *,
    db_path: str = "",
    apply: bool = False,
    limit: int = 0,
    reset: bool = False,
    store: Any = None,
) -> dict[str, Any]:
    """Read what the source can support and write observations, nothing else.

    `reset` is the only destructive option and it clears *our* table, after the
    source has been opened successfully — which is the ordering that keeps a moved
    database from wiping the store it was supposed to rebuild.
    """
    from aos.core.memory.store import MemoryStore

    owns_store = store is None
    store = store or MemoryStore()
    path = source_path(db_path)
    if path is None:
        return {"ok": False, "reason": f"{ENV_BACKFILL_DB} is not set; nothing was read or written"}

    try:
        source = open_read_only(path)  # raises before any write if the source is absent
    except BackfillError as exc:
        return {"ok": False, "reason": str(exc)}

    try:
        report = probe(source)
        if not report["available"]["sessions"]:
            return {
                "ok": False,
                "reason": f"source has no readable session table: missing {report['missing']}",
            }

        if reset and apply:
            store._conn.execute("DELETE FROM observations WHERE source = 'backfill'")
            store._conn.commit()

        if reset:
            mark = {"watermark_time": 0, "watermark_id": "", "sessions_seen": 0}
        else:
            mark = store.backfill_watermark(WATERMARK_KEY)
        written = 0
        skipped = 0
        highest_time = int(mark["watermark_time"])
        highest_id = str(mark["watermark_id"])
        seen = 0

        for _row, evidence in iter_sessions(source, since_time=highest_time, since_id=highest_id, limit=limit):
            seen += 1
            if not evidence.has_evidence:
                skipped += 1
            else:
                written += _write(store, evidence, apply=apply)
            if (evidence.time_updated, evidence.session_id) > (highest_time, highest_id):
                highest_time, highest_id = evidence.time_updated, evidence.session_id

            # The watermark moves as it goes, not at the end: half a pass beats a
            # lost pass, and a re-run can only ever re-read the tail.
            if apply:
                store.set_backfill_watermark(
                    WATERMARK_KEY,
                    watermark_time=highest_time,
                    watermark_id=highest_id,
                    sessions_seen=int(mark["sessions_seen"]) + seen,
                )

        return {
            "ok": True,
            "applied": apply,
            "source": str(path),
            "sessions_seen": seen,
            "written": written,
            "skipped_without_evidence": skipped,
            "watermark": {"time": highest_time, "id": highest_id},
            "probe": report,
        }
    finally:
        source.close()
        if owns_store:
            store.close()


def _write(store: Any, evidence: SessionEvidence, *, apply: bool) -> int:
    if not apply:
        return 1
    loop_id = f"BACKFILL-{evidence.session_id}"
    existing = store.find_observation_by_loop(loop_id)
    if existing and existing["source_hash"] == evidence.fingerprint:
        return 0  # nothing about the counts changed since the last read
    if existing:
        store.update_observation_fingerprint(
            int(existing["observation_id"]),
            signals=evidence.signals(),
            source_hash=evidence.fingerprint,
        )
        return 1
    store.add_observation(
        loop_id=loop_id,
        task_id=evidence.session_id,
        session_id=evidence.session_id,
        outcome="partial",
        quality_score=0.0,
        source_hash=evidence.fingerprint,
        confidence=0.0,
        needs_review=True,
        synthesised=False,
        signals=evidence.signals(),
        source="backfill",
    )
    return 1
