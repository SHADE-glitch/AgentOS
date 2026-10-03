"""Read-only recall over basic-memory notes.

The engine never owns these notes: it opens the neighbour's SQLite index with
`mode=ro`, never writes, and injects **pointers** (title + permalink + file path)
labelled as unverified human notes. The three properties this file exists to keep
are: it cannot write, it cannot be mistaken for Agent OS experience, and it cannot
break a preflight when the neighbour's database is missing, locked or reshaped.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from aos.config import basic_memory_db
from aos.core.memory import external, inject, policy


def make_bm_db(path: Path, notes: list[dict]) -> Path:
    """A neighbour database shaped like basic-memory 0.23's index."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE entity (id INTEGER PRIMARY KEY, title TEXT, note_type TEXT,"
        " permalink TEXT, file_path TEXT, entity_metadata TEXT, project_id INTEGER)"
    )
    conn.execute("CREATE TABLE note_content (entity_id INTEGER, markdown_content TEXT)")
    for index, note in enumerate(notes, start=1):
        fields = {"title": note["title"], "type": "note", "tags": note.get("tags", [])}
        fields.update(note.get("metadata") or {})
        metadata = json.dumps(fields)
        conn.execute(
            "INSERT INTO entity (id, title, note_type, permalink, file_path, entity_metadata, project_id)"
            " VALUES (?, ?, 'note', ?, ?, ?, 1)",
            (index, note["title"], note.get("permalink", f"main/note-{index}"),
             note.get("path", f"notes/note-{index}.md"), metadata),
        )
        conn.execute("INSERT INTO note_content (entity_id, markdown_content) VALUES (?, ?)",
                     (index, note.get("body", "")))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def bm_db(tmp_path, monkeypatch):
    path = make_bm_db(tmp_path / "basic-memory" / "memory.db", [
        {"title": "会话总结-GNOME系统运维精华", "tags": ["gnome", "运维"], "permalink": "main/gnome-ops",
         "path": "90-archive/gnome-ops.md", "body": "重启 gnome-shell 用 ALT+F2 r。"},
        {"title": "Java后端项目经验", "tags": ["java", "spring-boot"], "permalink": "main/java-notes",
         "path": "90-archive/java-notes.md", "body": "Spring Boot 的 profile 覆盖顺序。"},
        {"title": "无标签的一篇", "tags": [], "permalink": "main/plain", "path": "plain.md",
         "body": "只有一句：permalink 才是稳定标识。"},
    ])
    monkeypatch.setenv("AOS_BM_DB", str(path))
    policy.reload()
    return path


def test_the_configured_path_is_overridable_and_home_relative(monkeypatch, tmp_path):
    """`config.py` is the only place a path may be written down."""
    monkeypatch.delenv("AOS_BM_DB", raising=False)
    assert basic_memory_db() == Path.home() / ".basic-memory" / "memory.db"
    monkeypatch.setenv("AOS_BM_DB", str(tmp_path / "elsewhere.db"))
    assert basic_memory_db() == tmp_path / "elsewhere.db"


def test_a_note_is_recalled_as_a_pointer_and_labelled_unverified(bm_db):
    rows = external.recall("帮我看看 gnome 运维 的 会话总结", k=3)
    assert rows, "a title/tag overlap must recall the note"
    row = rows[0]
    assert row["external"] is True
    assert row["source"] == "basic-memory"
    assert row["memory_id"] == "bm:main/gnome-ops", "the id is the neighbour's permalink, not ours"
    assert row["evidence_level"] == "external"
    assert row["confidence"] == "", "an empty confidence is honest: no gate ever ran on this"
    assert row["lane"] == "external"
    assert row["is_hypothesis"] is False
    assert row["permalink"] == "main/gnome-ops"
    assert row["path"] == "90-archive/gnome-ops.md"


def test_nothing_is_recalled_when_the_database_is_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("AOS_BM_DB", str(tmp_path / "never-created" / "memory.db"))
    policy.reload()
    assert external.recall("gnome 运维") == []


def test_a_database_without_the_expected_tables_is_not_an_error(bm_db, monkeypatch):
    """basic-memory can be migrated or half-written; either way preflight proceeds."""
    conn = sqlite3.connect(bm_db)
    conn.execute("DROP TABLE note_content")
    conn.commit()
    conn.close()
    assert external.recall("gnome 运维") == []


def test_an_unreadable_query_cannot_take_the_loop_down(bm_db, monkeypatch):
    monkeypatch.setattr(external, "_open_ro", lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    assert external.recall("anything") == []


def test_the_reader_issues_no_write_statement_and_leaves_the_bytes_alone(bm_db):
    """Read-only is asserted twice: the source contains no writes, and the file does not move."""
    source = Path(external.__file__).read_text(encoding="utf-8")
    executable = re.sub(r'""".*?"""', "", source, flags=re.S)
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|ATTACH|VACUUM)\b", executable, re.I), (
        "the neighbour's database is never ours to modify")
    before = hashlib.sha256(bm_db.read_bytes()).hexdigest()
    external.recall("gnome 运维 java", k=3)
    assert hashlib.sha256(bm_db.read_bytes()).hexdigest() == before


def test_queries_are_matched_by_overlap_not_by_assumption(bm_db):
    """An unrelated question must not drag in a note that shares nothing with it."""
    assert [row["permalink"] for row in external.recall("kubernetes helm chart 升级", k=3)] == []
    hits = {row["permalink"] for row in external.recall("java spring-boot 后端", k=3)}
    assert hits == {"main/java-notes"}


def test_punctuation_is_not_what_decides_a_pointer(bm_db):
    """A note tagged `spring-boot` must still answer a question written "Spring Boot".

    Without the separator-insensitive pass, the section is silently empty in exactly
    the cases it exists for — and an empty section looks identical to "no relevant note".
    """
    assert [row["permalink"] for row in external.recall("帮我把 Spring Boot 的 profile 分环境")] == ["main/java-notes"]
    assert external.recall("kubernetes helm chart 升级") == []


def test_disabled_policy_reads_nothing_at_all(bm_db, tmp_path, monkeypatch):
    """`enabled: false` means the file is not opened, not that its rows are filtered."""
    policies = tmp_path / "content" / "policies"
    policies.mkdir(parents=True)
    (policies / "external.json").write_text(json.dumps({"enabled": False}), encoding="utf-8")
    monkeypatch.setenv("AOS_CONTENT_DIR", str(tmp_path / "content"))
    policy.reload()
    assert external.recall("gnome 运维 会话总结") == []


def test_a_note_appears_once_even_when_the_index_holds_two_rows(tmp_path, monkeypatch):
    path = make_bm_db(tmp_path / "dup.db", [{"title": "重复的一篇", "tags": ["dup"], "permalink": "main/dup"}] * 2)
    monkeypatch.setenv("AOS_BM_DB", str(path))
    policy.reload()
    rows = external.recall("dup 重复的一篇", k=5)
    assert [row["memory_id"] for row in rows] == ["bm:main/dup"]


def test_a_note_this_engine_published_is_not_an_external_note(tmp_path, monkeypatch):
    """Agent OS's own published lesson is governed memory, not an unverified pointer.

    `external_write.build_note` marks every note it writes with `agent_os: true`, so a
    note carrying that marker is already recalled from the memory table. Counting it
    here too would show one lesson twice, under two contradictory labels.
    """
    path = make_bm_db(tmp_path / "ours.db", [
        {"title": "人写的 GNOME 笔记", "tags": ["gnome"], "permalink": "main/human"},
        {"title": "M-AB12CD34", "tags": ["gnome"], "permalink": "main/agent-os/m-ab12cd34",
         "metadata": {"agent_os": True, "aos_memory_id": "M-AB12CD34"}},
        {"title": "标了 false 的笔记", "tags": ["gnome"], "permalink": "main/not-ours",
         "metadata": {"agent_os": False}},
    ])
    monkeypatch.setenv("AOS_BM_DB", str(path))
    policy.reload()
    hits = {row["permalink"] for row in external.recall("gnome 运维", k=5)}
    assert hits == {"main/human", "main/not-ours"}, "only our own marker is skipped, and only when true"


def test_the_block_points_at_the_note_without_copying_its_body(bm_db):
    rows = external.recall("gnome 运维 会话总结", k=3)
    block = inject.render([], external=rows)
    assert "ALT+F2" not in block["text"], "the default budget is pointers only"
    assert "【以下为 basic-memory 的人工笔记，非 Agent OS 验证过的经验】" in block["text"]
    assert "外部笔记 · 未验证" in block["text"]
    assert "笔记：" in block["text"]
    assert "main/gnome-ops" in block["text"]


def test_body_chars_is_a_real_knob_not_a_decoration(bm_db, tmp_path, monkeypatch):
    policies = tmp_path / "content" / "policies"
    policies.mkdir(parents=True)
    (policies / "external.json").write_text(json.dumps({"enabled": True, "max_items": 3,
                                                        "max_body_chars": 40, "min_tag_overlap": 1}),
                                            encoding="utf-8")
    monkeypatch.setenv("AOS_CONTENT_DIR", str(tmp_path / "content"))
    policy.reload()
    block = inject.render([], external=external.recall("gnome 运维 会话总结", k=3))
    assert "ALT+F2" in block["text"], "raising the budget is what lets an excerpt through"


def test_an_empty_neighbour_leaves_the_injection_block_byte_identical(bm_db):
    """Nothing here may disturb a run that has no external hits — the disable-clean guarantee."""
    plain = inject.render([{"memory_id": "M-1", "type": "episodic", "title": "t", "body": "b",
                            "evidence_level": "hypothesis", "confidence": "low", "lane": "hypothesis",
                            "is_hypothesis": True, "status": "active", "scope": "global"}])
    with_nothing = inject.render([dict(plain["structured"][0])], external=[])
    assert with_nothing["text"] == plain["text"]
    assert with_nothing["memory_ids"] == plain["memory_ids"]
