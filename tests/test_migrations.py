"""Schema migration tests.

The store is the one component here that cannot be rebuilt from code: it holds
the experience the engine exists to accumulate. So every case below is about
either surviving data or refusing to proceed, and the interesting failure mode
is the one that looks like success — a migration that commits, bumps its
version, and quietly deletes rows on the way through.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aos.core.memory import migrations
from aos.core.memory.migrations import (
    BASELINE_VERSION,
    LATEST_VERSION,
    SchemaError,
    current_version,
    ensure_schema,
    migrate,
    pending_migrations,
)
from aos.core.memory.store import MemoryStore

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_SQL = (REPO_ROOT / "aos" / "core" / "memory" / "schema.sql").read_text(encoding="utf-8")

# The vocabulary v1 accepted. Written out rather than imported, because these
# tests must keep passing after the engine forgets them.
V1_TYPES = ("task", "pattern", "anti-pattern", "failure", "decision", "effectiveness", "hypothesis")


def _v1_connection(db_path: Path) -> sqlite3.Connection:
    """A database exactly as schema.sql builds it, stamped as the baseline."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(BASELINE_SQL)
    conn.execute(f"PRAGMA user_version = {BASELINE_VERSION}")
    conn.execute(
        "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
        (str(BASELINE_VERSION),),
    )
    conn.commit()
    return conn


def _insert_v1_memory(conn: sqlite3.Connection, memory_id: str, **fields) -> None:
    row = {
        "memory_id": memory_id,
        "type": "pattern",
        "category": "optimization",
        "title": f"title {memory_id}",
        "body": f"body {memory_id}",
        "difficulty": "medium",
        "evidence_level": "runtime_validated",
        "confidence": "high",
        "status": "active",
        "taxonomy_skill": "",
        "source_task": "",
        "performance_gain": 0.0,
        "decay_factor": 1.0,
        "observation_count": 3,
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-02T00:00:00+00:00",
    }
    row.update(fields)
    columns = ", ".join(row)
    marks = ", ".join("?" * len(row))
    conn.execute(f"INSERT INTO memories ({columns}) VALUES ({marks})", list(row.values()))


# ── the mechanism ──────────────────────────────────────────────────────
def test_a_new_file_is_built_at_the_baseline_and_walked_up_to_latest(tmp_path):
    db = tmp_path / "aos.db"
    conn = sqlite3.connect(str(db))
    report = ensure_schema(conn, db_path=db)

    assert report["applied"] == [m.describe() for m in migrations.MIGRATIONS]
    assert current_version(conn) == LATEST_VERSION
    # Nothing existed to lose, so no stray backup file beside a new store.
    assert report["backup"] is None
    assert list(tmp_path.glob("*.bak")) == []


def test_opening_an_up_to_date_database_twice_changes_nothing(tmp_path):
    db = tmp_path / "aos.db"
    conn = sqlite3.connect(str(db))
    ensure_schema(conn, db_path=db)

    before = current_version(conn)
    report = ensure_schema(conn, db_path=db)

    assert report["applied"] == []
    assert report["planned"] == []
    assert current_version(conn) == before


def test_the_mirror_in_schema_meta_tracks_pragma_user_version(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    migrate(conn, db_path=db)

    mirror = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0]
    assert int(mirror) == current_version(conn) == LATEST_VERSION


def test_dry_run_reports_without_writing(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.commit()

    report = migrate(conn, dry_run=True, db_path=db)

    assert report["planned"] == [m.describe() for m in migrations.MIGRATIONS]
    assert report["applied"] == []
    assert current_version(conn) == BASELINE_VERSION
    assert not list(tmp_path.glob("*.bak"))


def test_a_newer_database_than_the_engine_is_refused_not_downgraded(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 1}")
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
                 (str(LATEST_VERSION + 1),))
    conn.commit()

    with pytest.raises(SchemaError, match="newer than this engine"):
        ensure_schema(conn, db_path=db)

    assert current_version(conn) == LATEST_VERSION + 1


def test_a_downgrade_is_refused(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    migrate(conn, db_path=db)

    with pytest.raises(SchemaError, match="downgrade"):
        migrate(conn, to=BASELINE_VERSION, db_path=db)


def test_disagreeing_version_records_are_refused_rather_than_guessed(tmp_path):
    """user_version says one thing, schema_meta another: the file is not trusted."""
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    conn.execute("UPDATE schema_meta SET value = '9' WHERE key = 'schema_version'")
    conn.commit()

    with pytest.raises(SchemaError, match="disagree"):
        ensure_schema(conn, db_path=db)


def test_a_non_numeric_mirror_is_refused(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    conn.execute("UPDATE schema_meta SET value = 'v1-ish' WHERE key = 'schema_version'")
    conn.commit()

    with pytest.raises(SchemaError, match="not an integer"):
        ensure_schema(conn, db_path=db)


def test_auto_migration_can_be_switched_off_for_a_production_store(tmp_path, monkeypatch):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.commit()
    monkeypatch.setenv("AOS_NO_AUTO_MIGRATE", "1")

    with pytest.raises(SchemaError, match="AOS_NO_AUTO_MIGRATE"):
        ensure_schema(conn, db_path=db)

    assert current_version(conn) == BASELINE_VERSION
    # A second, deliberate migration still works: the switch refuses the silent
    # path, not the ability to migrate at all.
    monkeypatch.delenv("AOS_NO_AUTO_MIGRATE")
    report = ensure_schema(conn, db_path=db)
    assert report["applied"] == [m.describe() for m in migrations.MIGRATIONS]


def test_a_failing_migration_leaves_the_database_at_the_previous_version(tmp_path, monkeypatch):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.commit()

    def boom(_conn):
        raise RuntimeError("half way through a DROP TABLE")

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (migrations.MIGRATIONS[0], migrations.Migration(3, "will_fail", boom, destructive=True)),
    )

    with pytest.raises(SchemaError, match="will_fail"):
        # The ceiling is read from MIGRATIONS at call time, so the injected
        # step is picked up without restating the target version.
        migrate(conn, db_path=db)

    assert current_version(conn) == 2
    assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_pending_migrations_only_lists_what_is_missing(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)

    assert [m.version for m in pending_migrations(BASELINE_VERSION)] == [
        m.version for m in migrations.MIGRATIONS
    ]
    migrate(conn, db_path=db)
    assert pending_migrations(LATEST_VERSION) == []


# ── v2: the memory lifecycle ───────────────────────────────────────────
def test_v2_adds_the_lifecycle_columns(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    migrate(conn, db_path=db)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
    for expected in (
        "scope", "lane", "when_to_apply", "dedupe_key", "version", "supersedes",
        "last_verified_at", "revalidate_after", "source_project", "source_session",
        "source_evidence", "source_loop_id", "use_count", "success_count", "last_used_at",
    ):
        assert expected in columns
    # The two columns that were written-but-never-read or read-but-never-written.
    assert "taxonomy_skill" not in columns
    assert "performance_gain" not in columns


def test_v1_rows_survive_and_are_mapped_to_the_new_vocabulary(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    for v1_type in V1_TYPES:
        _insert_v1_memory(conn, f"M-{v1_type}", type=v1_type)
    _insert_v1_memory(conn, "M-validated", type="pattern", status="validated",
                      evidence_level="runtime_validated", updated_at="2026-09-09T00:00:00+00:00")
    _insert_v1_memory(conn, "M-degraded", type="failure", status="degraded", decay_factor=0.8)
    _insert_v1_memory(conn, "M-archived", type="decision", status="archived_candidate")
    conn.commit()

    migrate(conn, db_path=db)

    rows = {r["memory_id"]: dict(r) for r in conn.execute("SELECT * FROM memories").fetchall()}
    assert len(rows) == len(V1_TYPES) + 3
    assert rows["M-task"]["type"] == "episodic"
    assert rows["M-pattern"]["type"] == "procedural"
    assert rows["M-anti-pattern"]["type"] == "failure"
    assert rows["M-decision"]["type"] == "semantic"
    assert rows["M-effectiveness"]["type"] == "semantic"
    assert rows["M-failure"]["type"] == "failure"
    # A v1 row whose type said `hypothesis` keeps its facts and moves the claim
    # to the lane, where one column answers the question instead of three.
    assert rows["M-hypothesis"]["type"] == "semantic"
    assert rows["M-hypothesis"]["lane"] == "hypothesis"
    assert rows["M-validated"]["status"] == "verified"
    assert rows["M-validated"]["last_verified_at"] == "2026-09-09T00:00:00+00:00"
    assert rows["M-degraded"]["status"] == "deprecated"
    assert rows["M-archived"]["status"] == "archived"
    # Numbers are carried across untouched, not recomputed.
    assert rows["M-degraded"]["decay_factor"] == pytest.approx(0.8)
    assert rows["M-pattern"]["observation_count"] == 3
    assert rows["M-validated"]["difficulty"] == "medium"


def test_taxonomy_skill_is_folded_into_category_rather_than_dropped(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1", taxonomy_skill="bugfix", category="optimization")
    _insert_v1_memory(conn, "M2", taxonomy_skill="", category="optimization")
    conn.commit()

    migrate(conn, db_path=db)

    rows = {r[0]: r[1] for r in conn.execute("SELECT memory_id, category FROM memories")}
    assert rows["M1"] == "bugfix"
    assert rows["M2"] == "optimization"


def test_tags_and_roles_are_not_cascaded_away_by_the_rebuild(tmp_path):
    """The regression this migration was actually written to be checked against.

    Rebuilding `memories` means dropping it, and memory_tags/memory_roles
    reference it ON DELETE CASCADE. `PRAGMA foreign_keys = OFF` is ignored inside
    an open transaction, so a rebuild that turns it off after BEGIN silently
    deletes every tag and role — and passes, because the scoring code tolerates
    an empty tag list.
    """
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1", type="pattern")
    conn.execute("INSERT INTO memory_tags(memory_id, tag) VALUES ('M1', 'cache-key')")
    conn.execute("INSERT INTO memory_tags(memory_id, tag) VALUES ('M1', 'redis')")
    conn.execute("INSERT INTO memory_roles(memory_id, role) VALUES ('M1', 'backend-architect')")
    conn.commit()

    migrate(conn, db_path=db)

    assert [r[0] for r in conn.execute("SELECT tag FROM memory_tags WHERE memory_id = 'M1'")] == [
        "cache-key",
        "redis",
    ]
    assert [r[0] for r in conn.execute("SELECT role FROM memory_roles")] == ["backend-architect"]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_observations_and_reviews_survive(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.execute(
        "INSERT INTO observations(memory_id, loop_id, outcome, quality_score, created_at) "
        "VALUES ('M1', 'L1', 'success', 4.2, '2026-09-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO candidates(target_memory, candidate_type, loop_id, created_at) "
        "VALUES ('M1', 'reinforce', 'L1', '2026-09-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO learning_reviews(memory_id, candidate_id, status, created_at) "
        "VALUES ('M1', 1, 'pending', '2026-09-01T00:00:00+00:00')"
    )
    conn.commit()

    migrate(conn, db_path=db)

    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1
    assert conn.execute("SELECT status FROM learning_reviews").fetchone()[0] == "pending"


def test_a_destructive_migration_backs_the_file_up_first(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.commit()

    report = migrate(conn, db_path=db)

    backup = Path(report["backup"])
    first_destructive = next(m for m in migrations.MIGRATIONS if m.destructive)
    assert backup.exists()
    # Named for the first destructive step, not for the ceiling: v3 is additive
    # and cannot lose anything, so the copy that matters is the one taken before
    # the table rebuild.
    assert backup.name == f"aos.db.pre-v{first_destructive.version}.bak"
    # The backup is the pre-migration database, not a copy of the migrated one:
    # it must still answer to the v1 column set to be worth anything.
    preserved = sqlite3.connect(str(backup))
    columns = {row[1] for row in preserved.execute("PRAGMA table_info(memories)")}
    assert "taxonomy_skill" in columns
    assert preserved.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
    preserved.close()


def test_a_file_whose_schema_is_ahead_of_its_stamp_is_refused_with_a_repair_path(tmp_path):
    """Hand-edited pragma or a mismatched restore: say so, do not rebuild twice.

    The DDL and the version bump commit together, so a healthy install cannot
    get here. Without the check the symptom is `no such column: taxonomy_skill`
    raised from inside the rebuild, which reads like a broken migration rather
    than like a file that was already migrated.
    """
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    ensure_schema(conn, db_path=db)
    # Same file, same tables, stamped back a version.
    conn.execute(f"PRAGMA user_version = {BASELINE_VERSION}")
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
                 (str(BASELINE_VERSION),))
    conn.commit()

    with pytest.raises(SchemaError, match="already has the v2 columns"):
        ensure_schema(conn, db_path=db)

    assert current_version(conn) == BASELINE_VERSION
    assert "lane" in _columns_of(conn, "memories")


def test_the_new_vocabulary_is_enforced_by_the_schema(tmp_path):
    """After v2 the store itself rejects the old words.

    A CHECK that never fails is the usual way a migrated vocabulary ends up with
    both dialects in one table, and recall then quietly matches neither.
    """
    db = tmp_path / "aos.db"
    store = MemoryStore(db_path=db)
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_memory({"memory_id": "M1", "type": "pattern", "title": "t", "body": "b"})
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_memory({"memory_id": "M2", "type": "procedural", "status": "validated",
                             "title": "t", "body": "b"})
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_memory({"memory_id": "M3", "type": "procedural", "decay_factor": 1.7,
                             "title": "t", "body": "b"})
    store.close()


def test_an_upsert_does_not_zero_the_counters_the_loop_earned(tmp_path):
    """A re-seed rewrites what a memory says, not what has happened to it."""
    db = tmp_path / "aos.db"
    store = MemoryStore(db_path=db)
    row = {"memory_id": "M1", "type": "procedural", "title": "first wording", "body": "b"}
    store.upsert_memory(row)
    store.update_memory_fields("M1", use_count=7, success_count=5, observation_count=9,
                               decay_factor=0.6, last_used_at="2026-09-20T00:00:00+00:00")

    store.upsert_memory({**row, "title": "reworded by a reviewer"})

    after = store.get_memory("M1")
    assert after["title"] == "reworded by a reviewer"
    assert (after["use_count"], after["success_count"]) == (7, 5)
    assert after["observation_count"] == 9
    assert after["decay_factor"] == pytest.approx(0.6)
    assert after["last_used_at"] == "2026-09-20T00:00:00+00:00"
    store.close()


def test_a_real_v1_store_opens_reads_and_writes_after_migrating(tmp_path, monkeypatch):
    """The whole point: an existing installation is still usable, not just valid."""
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M-old", type="anti-pattern", category="bugfix",
                      evidence_level="runtime_validated", status="active")
    conn.execute("INSERT INTO memory_tags(memory_id, tag) VALUES ('M-old', 'crash')")
    conn.commit()
    conn.close()

    monkeypatch.setenv("AOS_DB_PATH", str(db))
    store = MemoryStore(db_path=db)
    assert current_version(store.conn) == LATEST_VERSION

    recalled = [m["memory_id"] for m in store.memories_for_scoring()]
    assert recalled == ["M-old"]
    scored = store.memories_for_scoring()[0]
    assert scored["type"] == "failure"
    assert scored["tags"] == ["crash"]

    store.upsert_memory(
        {"memory_id": "M-new", "type": "constraint", "title": "t", "body": "b",
         "scope": "project:AgentOS", "when_to_apply": "before adding a dependency"},
        tags=["stdlib"],
    )
    assert store.get_memory("M-new")["scope"] == "project:AgentOS"
    store.close()


# ── v3: what the learning loop records about its own reasoning ─────────
def test_v3_adds_signals_consumption_and_review_kind(tmp_path):
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    migrate(conn, db_path=db)

    obs = _columns_of(conn, "observations")
    assert {"confidence", "signals_json", "needs_review", "synthesised", "skill_used"} <= obs
    cand = _columns_of(conn, "candidates")
    assert {"consumed_at", "consumed_by"} <= cand
    reviews = _columns_of(conn, "learning_reviews")
    assert {"kind", "outcome"} <= reviews


def test_v3_defaults_keep_pre_existing_rows_verifiable(tmp_path):
    """An old observation must not read as "human confirmed, no review needed".

    The default is the *suspicious* side: confidence 1.0 but needs_review 0 and
    synthesised 0 says "this verdict was reported to us", which is what a v2 row
    actually was. A default of needs_review=1 would flood the label queue with
    history nobody can relabel.
    """
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.execute(
        "INSERT INTO observations(memory_id, loop_id, outcome, quality_score, created_at) "
        "VALUES ('M1', 'L1', 'success', 4.0, '2026-09-01T00:00:00+00:00')"
    )
    conn.commit()

    migrate(conn, db_path=db)

    row = conn.execute("SELECT * FROM observations").fetchone()
    assert row["needs_review"] == 0
    assert row["synthesised"] == 0
    assert row["confidence"] == pytest.approx(1.0)
    assert json.loads(row["signals_json"]) == {}


def test_v3_is_additive_and_needs_no_backup(tmp_path):
    """A migration that only adds columns must not leave a .bak behind.

    Otherwise every store that upgrades pays a full file copy for a change that
    cannot lose data, and the presence of backups stops meaning "something
    destructive happened here".
    """
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    _insert_v1_memory(conn, "M1")
    conn.commit()

    destructive = migrate(conn, to=2, db_path=db)
    assert destructive["backup"], "v2 rebuilds the table, so it must copy the file first"
    Path(destructive["backup"]).unlink()

    additive = migrate(conn, db_path=db)
    assert additive["applied"] == ["v3 learning_signals", "v4 review_loop_link"]
    assert additive["backup"] is None
    assert list(tmp_path.glob("*.bak")) == []


def test_v4_lets_a_review_belong_to_a_loop(tmp_path):
    """An outcome review questions a run, so it needs the run's identity.

    Without a column the queue could not ask "does this loop already have an open
    review", and the sweep that opens them would stop being idempotent.
    """
    db = tmp_path / "aos.db"
    conn = _v1_connection(db)
    migrate(conn, db_path=db)

    assert "loop_id" in _columns_of(conn, "learning_reviews")
    conn.execute(
        "INSERT INTO learning_reviews (memory_id, loop_id, kind, created_at)"
        " VALUES ('', 'L-7', 'outcome_label', '2026-09-30T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO learning_reviews (memory_id, kind, created_at)"
        " VALUES ('M-1', 'promotion', '2026-09-30T00:00:00+00:00')"
    )
    conn.commit()

    rows = {
        r["kind"]: r
        for r in conn.execute("SELECT * FROM learning_reviews ORDER BY review_id")
    }
    assert rows["outcome_label"]["loop_id"] == "L-7"
    assert rows["outcome_label"]["status"] == "pending"
    # A promotion review still has no loop, so the two kinds cannot be mistaken
    # for each other by an empty-string match.
    assert rows["promotion"]["loop_id"] == ""


def _columns_of(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
