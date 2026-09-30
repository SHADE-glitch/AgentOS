"""Schema migrations, versioned by ``PRAGMA user_version``.

``schema.sql`` is the frozen **v1 baseline**: it is what a brand new database is
built from, and it is never edited to change an existing installation. Every
change after that is a named migration here, so "when did this column appear"
has one answer instead of three.

``PRAGMA user_version`` is the authority rather than a row in ``schema_meta``:
it lives in the file header, it commits atomically with the transaction that
bumps it, and it does not depend on a table that might itself be mid-migration.
``schema_meta.schema_version`` is kept as a readable mirror, and a disagreement
between the two is treated as corruption rather than as a thing to guess about.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

BASELINE_VERSION = 1
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# A migration that rebuilds a table. The whole file is copied aside before one
# of these, so a failed rebuild can be restored instead of read out of a journal.
ENV_NO_AUTO_MIGRATE = "AOS_NO_AUTO_MIGRATE"


class SchemaError(RuntimeError):
    """The database cannot be opened safely at its current version."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
    destructive: bool = False

    def describe(self) -> str:
        return f"v{self.version} {self.name}"


def current_version(conn: sqlite3.Connection) -> int:
    """The database's schema version, 0 when the file has never been stamped."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def latest_version() -> int:
    """The engine's schema ceiling, taken from ``MIGRATIONS`` at call time.

    A function rather than a constant, so appending a migration cannot leave the
    "newer than this engine" guard arguing with the list it is supposed to match.
    """
    return max([m.version for m in MIGRATIONS], default=BASELINE_VERSION)


def pending_migrations(from_version: int, to: Optional[int] = None) -> list["Migration"]:
    target = latest_version() if to is None else int(to)
    return [m for m in MIGRATIONS if from_version < m.version <= target]


def _check_mirror(conn: sqlite3.Connection, version: int) -> None:
    """Refuse a database whose two version records disagree.

    Either could be the lie, and the difference between them decides whether
    data is missing or merely unvalidated. Guessing is not an option.
    """
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        return
    # Read by index: this module must work on a bare connection as well as on
    # MemoryStore's row_factory one.
    raw = row[0]
    try:
        mirror = int(str(raw).strip())
    except ValueError:
        raise SchemaError(
            f"schema_meta.schema_version = {raw!r} is not an integer while "
            f"PRAGMA user_version says v{version}; refusing to guess. Repair one of "
            "them deliberately or restore a backup."
        ) from None
    if mirror != version:
        raise SchemaError(
            f"schema_meta says v{mirror} but PRAGMA user_version says v{version}. The "
            "two disagree, so this database is not trusted: restore a backup or repair "
            "one of them on purpose."
        )


def installed_version(conn: sqlite3.Connection) -> int:
    """Version of an existing database, stamping a freshly built baseline.

    A file ``schema.sql`` just created reports ``user_version = 0``: that is the
    baseline, not an unknown state. Anything above the last known migration is
    refused — reading a newer schema with an older engine is how a migration
    ends up being written backwards.
    """
    version = current_version(conn)
    if version == 0:
        conn.execute(f"PRAGMA user_version = {BASELINE_VERSION}")
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (str(BASELINE_VERSION),),
        )
        conn.commit()
        return BASELINE_VERSION
    if version > latest_version():
        raise SchemaError(
            f"database schema is v{version}, newer than this engine's v{latest_version()}; "
            "upgrade the engine rather than migrating the database backwards"
        )
    return version


def backup_path_for(db_path: Path, version: int) -> Path:
    return Path(db_path).with_name(f"{Path(db_path).name}.pre-v{version}.bak")


def _backup(conn: sqlite3.Connection, target: Path) -> Path:
    """Copy the live database to ``target`` with SQLite's own online backup."""
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    destination = sqlite3.connect(str(target))
    try:
        conn.backup(destination)
    finally:
        destination.close()
    return Path(target)


def _db_file(conn: sqlite3.Connection) -> Optional[str]:
    """The file backing this connection, when it is a file (not :memory:)."""
    row = conn.execute("PRAGMA database_list").fetchone()
    return row[2] if row and len(row) > 2 and row[2] else None


def _has_rows(conn: sqlite3.Connection) -> bool:
    """Whether anything could be lost. A baseline nobody has written to yet is
    not worth a backup file, and backing it up would litter every fresh store."""
    for table in ("memories", "observations", "candidates", "learning_reviews"):
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            return True
        if int(count) > 0:
            return True
    return False


def migrate(
    conn: sqlite3.Connection,
    *,
    to: Optional[int] = None,
    dry_run: bool = False,
    db_path: Optional[Path] = None,
    allow_backup: bool = True,
) -> dict[str, Any]:
    """Run every pending migration, one transaction each.

    ``dry_run`` answers "what would change" without writing, which is the only
    safe question to ask a production database. Each migration commits or rolls
    back alone, so a failure at v5 leaves v4 intact and reportable.
    """
    start = current_version(conn)
    ceiling = latest_version()
    target = ceiling if to is None else int(to)

    if target > ceiling:
        raise SchemaError(f"cannot migrate to v{target}; the last known version is v{ceiling}")
    if target < start:
        raise SchemaError(f"refusing to downgrade v{start} to v{target}")

    selected = pending_migrations(start, target)
    report: dict[str, Any] = {
        "from": start,
        "to": target,
        "applied": [],
        "planned": [m.describe() for m in selected],
        "backup": None,
        "dry_run": dry_run,
    }
    if dry_run or not selected:
        report["to"] = start
        return report

    resolved = db_path if db_path is not None else _db_file(conn)
    resolved_path = Path(resolved) if resolved else None
    if allow_backup and resolved_path is not None and _has_rows(conn):
        first_destructive = next((m for m in selected if m.destructive), None)
        if first_destructive is not None:
            target_backup = backup_path_for(resolved_path, first_destructive.version)
            if not target_backup.exists():
                _backup(conn, target_backup)
                report["backup"] = str(target_backup)

    for migration in selected:
        # Foreign keys must be toggled outside a transaction: SQLite ignores the
        # pragma while one is open, and a rebuild that drops a parent table with
        # FKs on cascades away the tag and role rows it exists to preserve.
        if migration.destructive:
            conn.execute("PRAGMA foreign_keys = OFF")
        # BEGIN IMMEDIATE so a second writer fails fast instead of interleaving
        # half-applied DDL with its own statements.
        conn.execute("BEGIN IMMEDIATE")
        try:
            migration.apply(conn)
            conn.execute(f"PRAGMA user_version = {migration.version}")
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(migration.version),),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            conn.execute("PRAGMA foreign_keys = ON")
            raise SchemaError(
                f"migration {migration.describe()} failed: {exc}; the database is "
                f"still at v{current_version(conn)}"
            ) from None
        conn.execute("PRAGMA foreign_keys = ON")
        report["applied"].append(migration.describe())

    report["to"] = current_version(conn)
    return report


def _has_baseline(conn: sqlite3.Connection) -> bool:
    """Whether this file already has the v1 tables.

    The baseline is DDL for a *new* database, so running it on an existing one is
    wrong in both directions: the CREATE TABLE guards are no-ops, but
    ``CREATE INDEX ... ON memories(taxonomy_skill)`` still executes and fails on
    any database already migrated past v1. That error looks like corruption and
    is really this function's absence.
    """
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memories'"
        ).fetchone()
        is not None
    )


def ensure_schema(conn: sqlite3.Connection, *, db_path: Optional[Path] = None) -> dict[str, Any]:
    """Build the baseline if needed, then bring the database up to date.

    Called on every store open. A backup is taken only when there are rows to
    lose, so a new installation is not born with a stray ``.bak`` beside it.

    With ``AOS_NO_AUTO_MIGRATE`` set, an outdated database is refused instead of
    rewritten: a production store should be backed up and migrated deliberately,
    by hand, at a chosen moment.
    """
    if not _has_baseline(conn):
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()

    version = installed_version(conn)
    _check_mirror(conn, version)

    if pending_migrations(version):
        if os.environ.get(ENV_NO_AUTO_MIGRATE, "").strip().lower() not in ("", "0", "false", "no"):
            raise SchemaError(
                f"database is at v{version} and this engine is at v{latest_version()}, but "
                f"{ENV_NO_AUTO_MIGRATE} is set. Take a backup, then run "
                "`aos memory migrate`."
            )
        return migrate(conn, db_path=db_path)

    return {
        "from": version,
        "to": version,
        "applied": [],
        "planned": [],
        "backup": None,
        "dry_run": False,
    }


# ── v1 → v2: the memory lifecycle ──────────────────────────────────────
#
# Column expressions are written against the *v1* table, and every target column
# is named explicitly, so a future edit to the baseline cannot silently reorder
# what a rebuild copies.
_V2_TYPE_MAP_SQL = """CASE type
            WHEN 'pattern' THEN 'procedural'
            WHEN 'task' THEN 'episodic'
            WHEN 'anti-pattern' THEN 'failure'
            WHEN 'failure' THEN 'failure'
            WHEN 'decision' THEN 'semantic'
            WHEN 'effectiveness' THEN 'semantic'
            WHEN 'hypothesis' THEN 'semantic'
            ELSE 'episodic'
        END"""

_V2_COLUMNS: dict[str, str] = {
    "memory_id": "memory_id",
    "type": _V2_TYPE_MAP_SQL,
    # taxonomy_skill duplicated `category` and was never read; its values were
    # the better vocabulary, so they are folded into category rather than lost.
    "category": "CASE WHEN COALESCE(taxonomy_skill, '') <> '' THEN taxonomy_skill ELSE COALESCE(category, '') END",
    "title": "COALESCE(title, '')",
    "body": "COALESCE(body, '')",
    "difficulty": "COALESCE(difficulty, '')",
    "evidence_level": "COALESCE(NULLIF(evidence_level, ''), 'hypothesis')",
    "confidence": "COALESCE(NULLIF(confidence, ''), 'low')",
    "status": """CASE status
            WHEN 'validated' THEN 'verified'
            WHEN 'degraded' THEN 'deprecated'
            WHEN 'archived_candidate' THEN 'archived'
            WHEN 'candidate' THEN 'candidate'
            ELSE 'active'
        END""",
    # `hypothesis` stops being a type and becomes an evidence state. It used to
    # be written three ways (type, evidence_level, an `H-` id prefix); the lane
    # column is the one place it is now expressed.
    "lane": "CASE WHEN type = 'hypothesis' OR COALESCE(evidence_level, '') = 'hypothesis' THEN 'hypothesis' ELSE 'standard' END",
    "scope": "'global'",
    "when_to_apply": "''",
    "dedupe_key": "''",
    "version": "1",
    "supersedes": "''",
    # A row the old gate had marked `validated` really was verified at the time;
    # its updated_at is the last moment anything confirmed it.
    "last_verified_at": "CASE WHEN status = 'validated' THEN COALESCE(updated_at, '') ELSE '' END",
    "revalidate_after": "''",
    "source_task": "COALESCE(source_task, '')",
    "source_project": "''",
    "source_session": "''",
    "source_evidence": "''",
    "source_loop_id": "''",
    "decay_factor": "COALESCE(decay_factor, 1.0)",
    "observation_count": "COALESCE(observation_count, 0)",
    "use_count": "0",
    "success_count": "0",
    "last_used_at": "''",
    "created_at": "created_at",
    "updated_at": "updated_at",
}


def _memories_ddl(table: str) -> str:
    return f"""
CREATE TABLE {table} (
    memory_id         TEXT PRIMARY KEY,
    type              TEXT NOT NULL CHECK (type IN
                        ('episodic', 'semantic', 'procedural', 'failure', 'preference', 'constraint')),
    category          TEXT NOT NULL DEFAULT '',
    title             TEXT NOT NULL DEFAULT '',
    body              TEXT NOT NULL DEFAULT '',
    -- Retained as review metadata; it no longer takes part in scoring.
    difficulty        TEXT NOT NULL DEFAULT '',
    evidence_level    TEXT NOT NULL DEFAULT 'hypothesis' CHECK (evidence_level IN
                        ('hypothesis', 'benchmark_evaluated', 'runtime_validated',
                         'independent_validated', 'real_project_validated', 'production_validated')),
    confidence        TEXT NOT NULL DEFAULT 'low' CHECK (confidence IN ('low', 'medium', 'high')),
    status            TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN
                        ('candidate', 'active', 'verified', 'deprecated',
                         'superseded', 'invalidated', 'archived')),
    lane              TEXT NOT NULL DEFAULT 'standard' CHECK (lane IN ('standard', 'hypothesis')),
    scope             TEXT NOT NULL DEFAULT 'global',
    when_to_apply     TEXT NOT NULL DEFAULT '',
    dedupe_key        TEXT NOT NULL DEFAULT '',
    version           INTEGER NOT NULL DEFAULT 1,
    supersedes        TEXT NOT NULL DEFAULT '',
    last_verified_at  TEXT NOT NULL DEFAULT '',
    revalidate_after  TEXT NOT NULL DEFAULT '',
    source_task       TEXT NOT NULL DEFAULT '',
    source_project    TEXT NOT NULL DEFAULT '',
    source_session    TEXT NOT NULL DEFAULT '',
    source_evidence   TEXT NOT NULL DEFAULT '',
    source_loop_id    TEXT NOT NULL DEFAULT '',
    decay_factor      REAL NOT NULL DEFAULT 1.0 CHECK (decay_factor BETWEEN 0.0 AND 1.0),
    observation_count INTEGER NOT NULL DEFAULT 0,
    use_count         INTEGER NOT NULL DEFAULT 0,
    success_count     INTEGER NOT NULL DEFAULT 0,
    last_used_at      TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
)
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _expect_v1_shape(conn: sqlite3.Connection) -> None:
    """Refuse to run v2 on a file that is already v2 in shape but stamped v1.

    The DDL and the version stamp commit in one transaction, so a healthy
    installation cannot reach this. A hand-edited ``user_version``, or a backup
    restored next to the wrong pragma, can — and without this check the failure
    is the cryptic ``no such column: taxonomy_skill`` from inside the rebuild.
    """
    columns = _columns(conn, "memories")
    if "lane" in columns and "taxonomy_skill" not in columns:
        raise SchemaError(
            "memories already has the v2 columns, but the file is stamped v1. The schema "
            "is ahead of its own version record: set PRAGMA user_version = 2 deliberately "
            "rather than letting a migration rebuild a table that is already rebuilt."
        )


def _v2_memory_lifecycle(conn: sqlite3.Connection) -> None:
    _expect_v1_shape(conn)
    _rebuild_table(conn, "memories", _memories_ddl("memories_v2_new"), _V2_COLUMNS)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
        CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        CREATE INDEX IF NOT EXISTS idx_mem_status ON memories(status);
        CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(scope);
        CREATE INDEX IF NOT EXISTS idx_mem_lane ON memories(lane);
        -- One fact per scope. The empty key is excluded so unnormalised rows
        -- (every memory authored before dedupe landed) never collide.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_dedupe
            ON memories(scope, dedupe_key) WHERE dedupe_key <> '';
        """
    )


def _v3_learning_signals(conn: sqlite3.Connection) -> None:
    """Add what the learning loop needs to record *how* it concluded anything.

    Purely additive, so no rebuild and no backup. The point of these columns is
    that an outcome without its signals is unverifiable: a reviewer looking at
    ``failure`` cannot tell whether the tests failed or the model simply gave up,
    and the engine cannot tell a synthesized verdict from one the host reported.
    """
    conn.executescript(
        """
        ALTER TABLE observations ADD COLUMN confidence   REAL NOT NULL DEFAULT 1.0;
        ALTER TABLE observations ADD COLUMN signals_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE observations ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE observations ADD COLUMN synthesised  INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE observations ADD COLUMN skill_used   TEXT NOT NULL DEFAULT '';

        ALTER TABLE candidates ADD COLUMN consumed_at TEXT;
        ALTER TABLE candidates ADD COLUMN consumed_by TEXT;

        ALTER TABLE learning_reviews ADD COLUMN kind    TEXT NOT NULL DEFAULT 'promotion';
        ALTER TABLE learning_reviews ADD COLUMN outcome TEXT NOT NULL DEFAULT '';

        CREATE INDEX IF NOT EXISTS idx_obs_review ON observations(needs_review);
        CREATE INDEX IF NOT EXISTS idx_cand_open ON candidates(consumed_at)
            WHERE consumed_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_reviews_kind ON learning_reviews(kind, status);
        """
    )


def _v4_review_loop(conn: sqlite3.Connection) -> None:
    """Link reviews to the loop they are about, not only to a memory.

    ``outcome_label`` reviews question a whole run — "was that a success?" — so
    they have no single target memory, and the queue has to answer "does this
    loop already have an open review?" without extracting a field out of a JSON
    snapshot with ``LIKE``. A column the query can use is cheaper than that
    query, and it is what makes the sweep that opens them idempotent.
    """
    conn.executescript(
        """
        ALTER TABLE learning_reviews ADD COLUMN loop_id TEXT NOT NULL DEFAULT '';

        CREATE INDEX IF NOT EXISTS idx_reviews_loop ON learning_reviews(loop_id)
            WHERE loop_id <> '';
        """
    )


def _rebuild_table(
    conn: sqlite3.Connection, table: str, ddl: str, column_map: dict[str, str]
) -> None:
    """Rebuild ``table`` under a new definition, mapping every column by name.

    SQLite can neither drop a column a foreign key depends on nor add a CHECK to
    an existing table, so a vocabulary change means create / copy / drop /
    rename. The caller is responsible for turning foreign keys off outside the
    transaction; dropping the parent with them on would cascade-delete the tag
    and role rows this exists to preserve.
    """
    staging = "memories_v2_staging" if table == "memories" else f"{table}_staging"
    columns = ", ".join(column_map)
    sources = ", ".join(column_map.values())

    conn.execute(f'DROP TABLE IF EXISTS "{staging}"')
    conn.execute(ddl.replace("memories_v2_new", staging, 1))
    conn.execute(f'INSERT INTO "{staging}" ({columns}) SELECT {sources} FROM {table}')
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f'ALTER TABLE "{staging}" RENAME TO {table}')

    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    if broken:
        raise SchemaError(
            f"rebuilding {table} left {len(broken)} dangling foreign key(s); "
            "the migration was rolled back with the transaction"
        )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(2, "memory_lifecycle", _v2_memory_lifecycle, destructive=True),
    Migration(3, "learning_signals", _v3_learning_signals),
    Migration(4, "review_loop_link", _v4_review_loop),
)

# Kept for display and for callers that want the ceiling without a call;
# everything internal asks latest_version(), which reads the list itself.
LATEST_VERSION = MIGRATIONS[-1].version
