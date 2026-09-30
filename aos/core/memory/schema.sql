-- Agent OS memory store (SQLite) — schema v1, the frozen baseline.
--
-- SQLite is the engine's source of truth for memory metadata, observations
-- and the learning pipeline. Human-readable memory bodies live in the `body`
-- column and may later be mirrored to the content layer.
--
-- THIS FILE DESCRIBES v1 AND DOES NOT CHANGE. It is what a brand new database is
-- built from, and `aos/core/memory/migrations.py` then walks it up to the
-- engine's current version; editing it to alter an existing installation would
-- skip every migration and leave live databases with no record of how they got
-- their columns. The enum comments below are the v1 vocabulary, which migrations
-- v2 replaces.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ── Memories ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    memory_id         TEXT PRIMARY KEY,
    type              TEXT NOT NULL,            -- task|effectiveness|pattern|anti-pattern|failure|decision|hypothesis
    category          TEXT DEFAULT '',
    title             TEXT DEFAULT '',
    body              TEXT DEFAULT '',
    difficulty        TEXT DEFAULT '',
    evidence_level    TEXT DEFAULT 'hypothesis',
    confidence        TEXT DEFAULT 'low',
    status            TEXT DEFAULT 'active',    -- active|degraded|archived_candidate
    taxonomy_skill    TEXT DEFAULT '',          -- abstract router skill id
    source_task       TEXT DEFAULT '',
    performance_gain  REAL DEFAULT 0.0,
    decay_factor      REAL DEFAULT 1.0,
    observation_count INTEGER DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_skill ON memories(taxonomy_skill);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag)
);

CREATE TABLE IF NOT EXISTS memory_roles (
    memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
    role      TEXT NOT NULL,
    PRIMARY KEY (memory_id, role)
);

-- ── Observations (outcomes of loops that used a memory) ────────────────
CREATE TABLE IF NOT EXISTS observations (
    observation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id       TEXT,                       -- NULL = loop-level observation
    loop_id         TEXT NOT NULL,
    task_id         TEXT DEFAULT '',
    session_id      TEXT DEFAULT '',
    outcome         TEXT NOT NULL,              -- success|failure|partial
    quality_score   REAL DEFAULT 0.0,
    source_hash     TEXT DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_memory ON observations(memory_id);
CREATE INDEX IF NOT EXISTS idx_observations_loop ON observations(loop_id);

-- ── Candidates (proposed memory changes awaiting validation) ───────────
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    target_memory   TEXT DEFAULT '',
    candidate_type  TEXT NOT NULL,              -- create|reinforce|weaken|create_hypothesis|new
    loop_id         TEXT DEFAULT '',
    execution_id    TEXT DEFAULT '',
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_target ON candidates(target_memory);
CREATE INDEX IF NOT EXISTS idx_candidates_type ON candidates(candidate_type);

-- ── Learning reviews (the human gate) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS learning_reviews (
    review_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id            TEXT DEFAULT '',
    candidate_id         INTEGER REFERENCES candidates(candidate_id) ON DELETE SET NULL,
    proposed_change_json TEXT NOT NULL DEFAULT '{}',
    evidence_json        TEXT NOT NULL DEFAULT '{}',
    status               TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    created_at           TEXT NOT NULL,
    reviewed_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_status ON learning_reviews(status);

-- ── Retrieval log ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS retrieval_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id  TEXT NOT NULL,
    loop_id    TEXT DEFAULT '',
    query_hash TEXT DEFAULT '',
    score      REAL DEFAULT 0.0,
    rank       INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retrieval_memory ON retrieval_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_loop ON retrieval_log(loop_id);

-- ── Telemetry events (readable, replaces write-only YAML) ─────────────
CREATE TABLE IF NOT EXISTS telemetry_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,
    loop_id      TEXT DEFAULT '',
    task_id      TEXT DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_type ON telemetry_events(event_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_loop ON telemetry_events(loop_id);
