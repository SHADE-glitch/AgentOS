"""SQLite-backed memory store.

The store is the engine's source of truth for memories, observations,
candidates, learning reviews, retrieval history and telemetry. All access
goes through :class:`MemoryStore`; nothing else opens the database.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aos.config import get_paths

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = "1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class MemoryStore:
    """A thin, explicit wrapper around the Agent OS SQLite database."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            paths = get_paths()
            paths.ensure_store()
            db_path = paths.db_path
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    # ── lifecycle ──────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── memories ───────────────────────────────────────────────────

    def upsert_memory(
        self,
        memory: dict[str, Any],
        *,
        tags: Optional[list[str]] = None,
        roles: Optional[list[str]] = None,
    ) -> str:
        """Insert or update a memory. Returns the memory id."""
        memory_id = memory.get("memory_id") or _new_id("M")
        now = _now()
        created_at = memory.get("created_at") or now
        self._conn.execute(
            """
            INSERT INTO memories (
                memory_id, type, category, title, body, difficulty,
                evidence_level, confidence, status, taxonomy_skill, source_task,
                performance_gain, decay_factor, observation_count,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(memory_id) DO UPDATE SET
                type=excluded.type,
                category=excluded.category,
                title=excluded.title,
                body=excluded.body,
                difficulty=excluded.difficulty,
                evidence_level=excluded.evidence_level,
                confidence=excluded.confidence,
                status=excluded.status,
                taxonomy_skill=excluded.taxonomy_skill,
                source_task=excluded.source_task,
                performance_gain=excluded.performance_gain,
                decay_factor=excluded.decay_factor,
                observation_count=excluded.observation_count,
                updated_at=excluded.updated_at
            """,
            (
                memory_id,
                memory.get("type", "task"),
                memory.get("category", ""),
                memory.get("title", ""),
                memory.get("body", ""),
                memory.get("difficulty", ""),
                memory.get("evidence_level", "hypothesis"),
                memory.get("confidence", "low"),
                memory.get("status", "active"),
                memory.get("taxonomy_skill", ""),
                memory.get("source_task", ""),
                float(memory.get("performance_gain", 0.0)),
                float(memory.get("decay_factor", 1.0)),
                int(memory.get("observation_count", 0)),
                created_at,
                now,
            ),
        )
        if tags is not None:
            self._conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
            self._conn.executemany(
                "INSERT OR IGNORE INTO memory_tags(memory_id, tag) VALUES (?, ?)",
                [(memory_id, str(t)) for t in tags],
            )
        if roles is not None:
            self._conn.execute("DELETE FROM memory_roles WHERE memory_id = ?", (memory_id,))
            self._conn.executemany(
                "INSERT OR IGNORE INTO memory_roles(memory_id, role) VALUES (?, ?)",
                [(memory_id, str(r)) for r in roles],
            )
        self._conn.commit()
        return memory_id

    def get_memory(self, memory_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def list_memories(
        self, *, type: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM memories {where} ORDER BY created_at, memory_id", params
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def delete_memory(self, memory_id: str) -> None:
        self._conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
        self._conn.commit()

    def set_decay_factor(self, memory_id: str, factor: float) -> None:
        self._conn.execute(
            "UPDATE memories SET decay_factor = ?, updated_at = ? WHERE memory_id = ?",
            (round(float(factor), 4), _now(), memory_id),
        )
        self._conn.commit()

    def set_observation_count(self, memory_id: str, count: int) -> None:
        self._conn.execute(
            "UPDATE memories SET observation_count = ?, updated_at = ? WHERE memory_id = ?",
            (int(count), _now(), memory_id),
        )
        self._conn.commit()

    def decay_factors(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT memory_id, decay_factor FROM memories").fetchall()
        return {r["memory_id"]: float(r["decay_factor"]) for r in rows}

    def count_memories(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()["n"])

    # ── scoring views ──────────────────────────────────────────────

    def memories_for_scoring(self) -> list[dict[str, Any]]:
        """Memories enriched with tags and roles, ready for scoring."""
        memories = self.list_memories()
        tags = self._group("SELECT memory_id, tag FROM memory_tags", "tag")
        roles = self._group("SELECT memory_id, role FROM memory_roles", "role")
        for mem in memories:
            mem["tags"] = tags.get(mem["memory_id"], [])
            mem["roles"] = roles.get(mem["memory_id"], [])
        return memories

    def usage_stats(self) -> dict[str, dict[str, Any]]:
        """Per-memory usage derived from observations and retrieval history."""
        stats: dict[str, dict[str, Any]] = {}
        rows = self._conn.execute(
            """
            SELECT memory_id, outcome, quality_score, created_at
            FROM observations
            WHERE memory_id IS NOT NULL
            """
        ).fetchall()
        for row in rows:
            entry = stats.setdefault(
                row["memory_id"],
                {"usage_count": 0, "successful_uses": 0, "last_used": None, "quality_scores": []},
            )
            entry["usage_count"] += 1
            if row["outcome"] == "success":
                entry["successful_uses"] += 1
            entry["quality_scores"].append(float(row["quality_score"]))
            entry["last_used"] = max(entry["last_used"] or "", row["created_at"])

        for row in self._conn.execute(
            "SELECT memory_id, MAX(created_at) AS last_retrieved FROM retrieval_log GROUP BY memory_id"
        ).fetchall():
            entry = stats.setdefault(
                row["memory_id"],
                {"usage_count": 0, "successful_uses": 0, "last_used": None, "quality_scores": []},
            )
            entry["last_retrieved"] = row["last_retrieved"]

        for entry in stats.values():
            uc = entry["usage_count"]
            entry["success_rate"] = (entry["successful_uses"] / uc) if uc else 0.5
        return stats

    def quality_stats(self) -> dict[str, float]:
        """Average quality score per memory (from observations)."""
        rows = self._conn.execute(
            """
            SELECT memory_id, AVG(quality_score) AS avg_quality
            FROM observations WHERE memory_id IS NOT NULL GROUP BY memory_id
            """
        ).fetchall()
        return {r["memory_id"]: float(r["avg_quality"] or 0.0) for r in rows}

    def global_avg_quality(self) -> float:
        row = self._conn.execute(
            "SELECT AVG(quality_score) AS avg_quality FROM observations WHERE memory_id IS NOT NULL"
        ).fetchone()
        return float(row["avg_quality"] or 0.0)

    # ── observations ───────────────────────────────────────────────

    def add_observation(
        self,
        *,
        loop_id: str,
        outcome: str,
        memory_id: Optional[str] = None,
        task_id: str = "",
        session_id: str = "",
        quality_score: float = 0.0,
        source_hash: str = "",
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO observations
                (memory_id, loop_id, task_id, session_id, outcome, quality_score, source_hash, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (memory_id, loop_id, task_id, session_id, outcome, float(quality_score), source_hash, _now()),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_observations(self, *, memory_id: Optional[str] = None) -> list[dict[str, Any]]:
        if memory_id:
            rows = self._conn.execute(
                "SELECT * FROM observations WHERE memory_id = ? ORDER BY observation_id", (memory_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM observations ORDER BY observation_id").fetchall()
        return [dict(r) for r in rows]

    # ── retrieval log ──────────────────────────────────────────────

    def log_retrieval(
        self, *, memory_id: str, score: float, rank: int, loop_id: str = "", query_hash: str = ""
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO retrieval_log (memory_id, loop_id, query_hash, score, rank, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (memory_id, loop_id, query_hash, float(score), int(rank), _now()),
        )
        self._conn.commit()

    def list_retrievals(self, *, memory_id: Optional[str] = None) -> list[dict[str, Any]]:
        if memory_id:
            rows = self._conn.execute(
                "SELECT * FROM retrieval_log WHERE memory_id = ? ORDER BY id", (memory_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM retrieval_log ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # ── candidates ─────────────────────────────────────────────────

    def add_candidate(
        self,
        *,
        candidate_type: str,
        target_memory: str = "",
        loop_id: str = "",
        execution_id: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO candidates
                (target_memory, candidate_type, loop_id, execution_id, payload_json, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                target_memory,
                candidate_type,
                loop_id,
                execution_id,
                json.dumps(payload or {}, ensure_ascii=False),
                _now(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_candidates(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM candidates ORDER BY candidate_id").fetchall()
        candidates = []
        for row in rows:
            candidate = dict(row)
            candidate["payload"] = json.loads(candidate.get("payload_json") or "{}")
            candidates.append(candidate)
        return candidates

    # ── learning reviews (the human gate) ──────────────────────────

    def add_review(
        self,
        *,
        memory_id: str,
        proposed_change: dict[str, Any],
        evidence: dict[str, Any],
        candidate_id: Optional[int] = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO learning_reviews
                (memory_id, candidate_id, proposed_change_json, evidence_json, status, created_at)
            VALUES (?,?,?,?, 'pending', ?)
            """,
            (
                memory_id,
                candidate_id,
                json.dumps(proposed_change, ensure_ascii=False),
                json.dumps(evidence, ensure_ascii=False),
                _now(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_review(self, review_id: int) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM learning_reviews WHERE review_id = ?", (int(review_id),)
        ).fetchone()
        return self._row_to_review(row) if row else None

    def list_reviews(self, *, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM learning_reviews WHERE status = ? ORDER BY review_id", (status,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM learning_reviews ORDER BY review_id"
            ).fetchall()
        return [self._row_to_review(r) for r in rows]

    def has_pending_review(self, memory_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM learning_reviews WHERE memory_id = ? AND status = 'pending' LIMIT 1",
            (memory_id,),
        ).fetchone()
        return row is not None

    def set_review_status(self, review_id: int, status: str) -> bool:
        cursor = self._conn.execute(
            "UPDATE learning_reviews SET status = ?, reviewed_at = ? WHERE review_id = ?",
            (status, _now(), int(review_id)),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ── telemetry ──────────────────────────────────────────────────

    def add_event(
        self, *, event_type: str, loop_id: str = "", task_id: str = "", payload: Optional[dict[str, Any]] = None
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO telemetry_events (event_type, loop_id, task_id, payload_json, created_at)
            VALUES (?,?,?,?,?)
            """,
            (event_type, loop_id, task_id, json.dumps(payload or {}, ensure_ascii=False), _now()),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_events(self, *, event_type: Optional[str] = None) -> list[dict[str, Any]]:
        if event_type:
            rows = self._conn.execute(
                "SELECT * FROM telemetry_events WHERE event_type = ? ORDER BY id", (event_type,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM telemetry_events ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # ── promotion writes ───────────────────────────────────────────

    # Fields the learning pipeline is allowed to change. Everything else on a
    # memory is author-owned content and must not be rewritten by promotion.
    _PROMOTABLE_FIELDS = frozenset(
        {
            "evidence_level",
            "confidence",
            "status",
            "observation_count",
            "decay_factor",
            "performance_gain",
        }
    )

    def update_memory_fields(self, memory_id: str, **fields: Any) -> bool:
        """Apply a whitelisted partial update to a memory. Returns True if applied."""
        updates = {k: v for k, v in fields.items() if k in self._PROMOTABLE_FIELDS}
        if not updates:
            return False
        assignments = ", ".join(f"{k} = ?" for k in updates)
        cursor = self._conn.execute(
            f"UPDATE memories SET {assignments}, updated_at = ? WHERE memory_id = ?",
            (*updates.values(), _now(), memory_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ── internals ──────────────────────────────────────────────────

    def _row_to_review(self, row: sqlite3.Row) -> dict[str, Any]:
        review = dict(row)
        review["proposed_change"] = json.loads(review.pop("proposed_change_json") or "{}")
        review["evidence"] = json.loads(review.pop("evidence_json") or "{}")
        return review

    def _group(self, sql: str, value_key: str) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for row in self._conn.execute(sql).fetchall():
            grouped.setdefault(row["memory_id"], []).append(row[value_key])
        return grouped

    def _row_to_memory(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)
