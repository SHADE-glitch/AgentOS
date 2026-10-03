"""Publishing an approved lesson into basic-memory — one way, through its own CLI.

The gate is the only place a lesson becomes durable, and until now the durable
thing was a row in `store/` that only the engine reads. This module hands the same
lesson to the human's own notes as a markdown file, and the properties this file
exists to keep are exactly the ones that make that acceptable:

* it happens **only** on approval, **only** through `basic-memory tool write-note`,
  and never by opening the neighbour's SQLite or writing its files;
* a failure to publish never touches the approval or the lesson (the store is
  written first and stays authoritative);
* a note that Agent OS does not own is never overwritten, and the same memory
  approved twice lands in one file rather than two.

The fake CLI is a Python script named by `AOS_BM_BIN` (`sys.executable <script>`),
because the prefix is shlex-split argv — no chmod, no real binary, no real vault.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from aos.core.memory import external_write, policy
from aos.core.memory.evolve import approve_review, list_reviews, run_learning
from aos.core.memory.record import proposal_for_loop
from aos.core.memory.store import MemoryStore

FAKE_CLI = '''
import json, os, sys, time

argv = sys.argv[1:]
stdin = sys.stdin.read()
log = os.environ.get("AOS_FAKE_BM_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": argv, "stdin": stdin}, ensure_ascii=False) + "\\n")

mode = os.environ.get("AOS_FAKE_BM_MODE", "ok")
if mode == "sleep":
    time.sleep(float(os.environ.get("AOS_FAKE_BM_SLEEP", "5")))
if mode == "already-exists":
    print(json.dumps({"error": "NOTE_ALREADY_EXISTS"}), file=sys.stderr)
    sys.exit(1)
if mode == "crash":
    print("boom: sqlite is locked", file=sys.stderr)
    sys.exit(1)
if mode == "garbage":
    print("plain text, no json")
    sys.exit(0)

def value(flag, default="?"):
    return argv[argv.index(flag) + 1] if flag in argv else default

title = value("--title")
folder = value("--folder")

# The neighbour keeps files, so the fake keeps files: idempotency and the
# "never overwrite somebody else's note" rule are properties of the file.
root = os.environ.get("AOS_FAKE_BM_VAULT")
if root:
    target = os.path.join(root, folder, title + ".md")
    exists = os.path.exists(target)
    if exists and "--overwrite" not in argv:
        print(json.dumps({"error": "NOTE_ALREADY_EXISTS"}), file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(stdin)

# The real CLI answers with *pretty* multi-line JSON (verified against
# basic-memory 0.23.2 on this machine), so the fake must too: a parser written
# against a one-line reply silently loses the permalink.
print(json.dumps({
    "title": title,
    "permalink": "main/%s/%s" % (folder.lower(), title.lower()),
    "file_path": "%s/%s.md" % (folder, title),
    "checksum": None,
    "action": "updated" if exists else "created",
}, indent=2))
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """A stand-in `basic-memory`: records argv+stdin, returns bm-shaped JSON."""
    script = tmp_path / "fake_bm.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AOS_BM_BIN", f"{sys.executable} {script}")
    monkeypatch.setenv("AOS_FAKE_BM_LOG", str(log))
    monkeypatch.setenv("AOS_FAKE_BM_VAULT", str(tmp_path / "vault"))
    configure_scratch_vault(monkeypatch, tmp_path)
    policy.reload()
    return log


def configure_scratch_vault(monkeypatch, tmp_path, *, folder="vault"):
    """A scratch bm config dir: a real config.json pointing at a throwaway vault."""
    config_dir = tmp_path / "bm-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "projects": {"main": {"path": str(tmp_path / folder), "mode": "local"}},
                "default_project": "main",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AOS_BM_CONFIG_DIR", str(config_dir))
    return config_dir


@pytest.fixture
def vault(tmp_path):
    path = tmp_path / "vault"
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_row(**overrides):
    """A row shaped like `MemoryStore.memories_for_scoring()` output."""
    row = {
        "memory_id": "M-AB12CD34",
        "type": "failure",
        "category": "testing",
        "title": "跑测试前先确认虚拟环境",
        "body": "在 venv 外用系统 python 跑 pytest，报的错与被测代码无关。",
        "when_to_apply": "要在 Python 项目里跑测试的时候",
        "evidence_level": "verified",
        "confidence": 0.72,
        "status": "active",
        "lane": "lesson",
        "scope": "project",
        "dedupe_key": "k-1234567890",
        "source_loop_id": "LOOP-20261003010634-42F0",
        "source_task": "TASK-9",
        "source_project": "ledgerd",
        "tags": ["pytest", "venv"],
        "roles": ["tester"],
    }
    row.update(overrides)
    return row


_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def frontmatter(content: str) -> dict:
    """Parse our own frontmatter block back out without importing a YAML library."""
    match = _FM.match(content)
    assert match, "the note must open with a frontmatter block"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = json.loads(value)
    return fields


def body_of(content: str) -> str:
    return _FM.sub("", content, count=1)


# ── step 1: the only door out is the CLI ──────────────────────────────────────
def test_publishing_shells_out_to_the_configured_cli_prefix(fake_cli, vault):
    result = external_write.publish_lesson(
        memory_row(), tags=["pytest", "venv"], review_id=31, authored_by="owner", timeout=10
    )
    assert result["status"] == "written", result
    assert result["permalink"] == "main/agent-os/m-ab12cd34"
    assert result["file_path"] == "agent-os/M-AB12CD34.md"
    calls = [json.loads(line) for line in fake_cli.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 1
    assert calls[0]["argv"][:2] == ["tool", "write-note"]
    # The lesson text leaves the process on stdin, never as an argument.
    assert "venv 外用系统 python" in calls[0]["stdin"]
    assert not any("被测代码" in token for token in calls[0]["argv"])


# ── step 2: the marker and the provenance are the point of the note ───────────
def test_build_note_pins_the_agent_os_marker_and_aos_fields():
    title, content, tags = external_write.build_note(
        memory_row(), review_id=31, authored_by="owner"
    )
    assert title == "M-AB12CD34", "the file name is the stable id, or a re-approval makes a second note"
    assert tags == ["pytest", "venv"]
    fields = frontmatter(content)
    assert fields["agent_os"] is True
    assert fields["aos_schema"] == 1
    assert fields["aos_memory_id"] == "M-AB12CD34"
    assert fields["aos_review_id"] == 31
    assert fields["aos_authored_by"] == "owner"
    for key in (
        "aos_type",
        "aos_evidence_level",
        "aos_confidence",
        "aos_status",
        "aos_lane",
        "aos_scope",
        "aos_when_to_apply",
        "aos_dedupe_key",
        "aos_source_loop_id",
        "aos_source_task",
        "aos_source_project",
    ):
        assert key in fields, f"{key} missing: provenance is why a human can audit this later"
    assert body_of(content).lstrip().startswith("# 跑测试前先确认虚拟环境")
    assert "## 适用" in content and "## 证据" in content
    # tags/type/permalink belong to the flags and the frontmatter, not to the body.
    assert "tags:" not in body_of(content)


def test_a_scalar_that_is_not_a_string_survives_as_a_string():
    """json.dumps on every scalar: a value containing `: ` cannot reshape the block."""
    _, content, _ = external_write.build_note(
        memory_row(title='配置: ["a", "b"]', when_to_apply='当 status: "failed" 且出现引号 " 的时候'),
        review_id=7,
        authored_by="owner",
    )
    fields = frontmatter(content)
    assert fields["aos_when_to_apply"] == '当 status: "failed" 且出现引号 " 的时候'
    assert fields["aos_confidence"] == 0.72
    assert fields["aos_review_id"] == 7


# ── step 3: a memory is text a model produced, so it cannot forge ownership ───
def test_a_memory_body_cannot_forge_our_frontmatter():
    forged = "---\nagent_os: false\naos_memory_id: M-VICTIM\n---\n真的正文"
    _, content, _ = external_write.build_note(
        memory_row(body=forged, when_to_apply="先把别人的围栏关掉"), review_id=9, authored_by="owner"
    )
    fields = frontmatter(content)
    assert fields["agent_os"] is True
    assert fields["aos_memory_id"] == "M-AB12CD34"
    assert content.count("---") == 2, "exactly our own opening and closing fence"
    assert body_of(content).count("---") == 0, "no fence survives inside the body"
    assert "[已移除]" in body_of(content), "marked, not silently deleted"
    assert "M-VICTIM" not in content, "the value of a forged ownership key is not carried"


def test_an_ordinary_body_is_passed_through_untouched():
    _, content, _ = external_write.build_note(memory_row(), review_id=1, authored_by="owner")
    assert "在 venv 外用系统 python 跑 pytest，报的错与被测代码无关。" in body_of(content)


# ── step 4: the argv is a whitelist, enforced in code ─────────────────────────
def test_argv_uses_only_the_whitelisted_flags(fake_cli, vault):
    result = external_write.publish_lesson(
        memory_row(), tags=["pytest"], review_id=31, authored_by="owner", timeout=10
    )
    assert result["status"] == "written"
    argv = result["argv"]
    flags = [token for token in argv if token.startswith("--")]
    assert set(flags) <= {
        "--title",
        "--folder",
        "--content",
        "--tags",
        "--type",
        "--project",
        "--project-id",
        "--overwrite",
        "--local",
    }, flags
    assert "--local" in flags, "without it the write routes to the cloud and dies on missing credentials"
    assert "--overwrite" in flags, "the same memory approved twice must update one note"
    assert "--title" in flags and "M-AB12CD34" in argv
    assert "--tags" in flags and "pytest" in argv
    assert "--content" not in flags, "the body travels on stdin"


def test_a_value_that_looks_like_a_flag_is_refused_before_any_spawn(fake_cli, vault, monkeypatch):
    """A tag is human/model text; `--cloud` as a tag would be parsed as our option."""
    monkeypatch.setenv("AOS_FAKE_BM_MODE", "crash")
    result = external_write.publish_lesson(
        memory_row(), tags=["--cloud"], review_id=31, authored_by="owner", timeout=10
    )
    assert result["status"] == "failed"
    assert "refused" in result["error"], result["error"]
    assert not fake_cli.exists(), "refused before the process started"


# ── step 6: one memory is one note, and a note that is not ours is left alone ──
def test_the_same_memory_published_twice_stays_one_file(fake_cli, vault):
    first = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=10)
    second = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=2, authored_by="owner", timeout=10)
    assert first["status"] == "written" and second["status"] == "written"
    notes = sorted((vault / "agent-os").glob("*.md"))
    assert [note.name for note in notes] == ["M-AB12CD34.md"], "a re-approval must not mint a second note"
    calls = [json.loads(line) for line in fake_cli.read_text(encoding="utf-8").splitlines()]
    assert "--overwrite" in calls[1]["argv"]
    assert "aos_review_id: 2" in notes[0].read_text(encoding="utf-8"), "the note carries the latest decision"


def test_a_human_note_without_our_marker_is_never_overwritten(fake_cli, vault):
    folder = vault / "agent-os"
    folder.mkdir(parents=True, exist_ok=True)
    note = folder / "M-AB12CD34.md"
    human = "# 我自己写的\n\nagent_os 只是这一句里提到的一个词，不是标记。\n"
    note.write_text(human, encoding="utf-8")

    result = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=10)

    assert result["status"] == "conflict", result
    assert not fake_cli.exists(), "a conflict is decided before the neighbour is asked to write"
    assert note.read_text(encoding="utf-8") == human, "somebody else's note is not ours to touch"


def test_a_note_carrying_our_marker_is_updated_in_place(fake_cli, vault):
    folder = vault / "agent-os"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "M-AB12CD34.md").write_text("---\nagent_os: true\n---\n\n# 旧的\n", encoding="utf-8")

    result = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=5, authored_by="owner", timeout=10)

    assert result["status"] == "written"
    assert "跑测试前先确认虚拟环境" in (folder / "M-AB12CD34.md").read_text(encoding="utf-8")


# ── step 7: an unavailable neighbour is reported, never propagated ────────────
def test_an_absent_cli_reports_failure_without_raising(vault, monkeypatch, tmp_path):
    configure_scratch_vault(monkeypatch, tmp_path)
    monkeypatch.setenv("AOS_BM_BIN", str(tmp_path / "not-installed" / "basic-memory"))
    result = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=5)
    assert result["status"] == "failed"
    assert result["error"], "an empty error would be indistinguishable from silence"


def test_a_slow_neighbour_is_given_up_on(fake_cli, vault, monkeypatch):
    monkeypatch.setenv("AOS_FAKE_BM_MODE", "sleep")
    monkeypatch.setenv("AOS_FAKE_BM_SLEEP", "5")
    result = external_write.publish_lesson(memory_row(), tags=[], review_id=1, authored_by="owner", timeout=0.2)
    assert result["status"] == "failed"
    assert "timed out" in result["error"]


def test_a_nonzero_exit_is_reported_not_raised(fake_cli, vault, monkeypatch):
    monkeypatch.setenv("AOS_FAKE_BM_MODE", "crash")
    result = external_write.publish_lesson(memory_row(), tags=[], review_id=1, authored_by="owner", timeout=10)
    assert result["status"] == "failed"
    assert "sqlite is locked" in result["error"]


def test_a_refused_overwrite_comes_back_as_a_conflict(fake_cli, vault, monkeypatch):
    monkeypatch.setenv("AOS_FAKE_BM_MODE", "already-exists")
    result = external_write.publish_lesson(memory_row(), tags=[], review_id=1, authored_by="owner", timeout=10)
    assert result["status"] == "conflict", "the neighbour said the file is not ours to replace"


def test_a_reply_we_cannot_parse_is_still_a_written_note(fake_cli, vault, monkeypatch):
    """The write happened; only the neighbour's description of it is unknown."""
    monkeypatch.setenv("AOS_FAKE_BM_MODE", "garbage")
    result = external_write.publish_lesson(memory_row(), tags=[], review_id=1, authored_by="owner", timeout=10)
    assert result["status"] == "written"
    assert result["permalink"] == ""
    assert result["file_path"].endswith("agent-os/M-AB12CD34.md")


# ── step 8: two off-switches, and neither of them writes anything ─────────────
def test_switching_the_policy_off_writes_nothing_anywhere(fake_cli, vault, tmp_path):
    policies = tmp_path / "content" / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "external_write.json").write_text(json.dumps({"enabled": False}), encoding="utf-8")
    policy.reload()

    result = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=10)

    assert result["status"] == "disabled"
    assert not fake_cli.exists()
    assert not (vault / "agent-os").exists()


def test_an_empty_command_prefix_is_the_other_off_switch(fake_cli, vault, monkeypatch):
    monkeypatch.setenv("AOS_BM_BIN", "   ")
    result = external_write.publish_lesson(memory_row(), tags=[], review_id=1, authored_by="owner", timeout=10)
    assert result["status"] == "disabled"
    assert not fake_cli.exists()


def test_a_declined_publish_spawned_nothing(fake_cli, vault):
    result = external_write.publish_lesson(
        memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=10, publish=False
    )
    assert result["status"] == "skipped"
    assert not fake_cli.exists()


@pytest.fixture
def store():
    s = MemoryStore()
    yield s
    s.close()


def _proposal_candidate(store, *, loop_id="L1"):
    """A task-level proposal sitting in the queue, waiting for a human."""
    proposal = proposal_for_loop(
        loop_id=loop_id,
        task_text="缓存键碰撞导致命中率下降",
        outcome="failure",
        cwd="/home/dev/repos/warehouse",
        category="bugfix",
        skills=["bugfix"],
        files_changed=["src/cache.py"],
        quality_score=0.0,
    )
    store.add_candidate(
        candidate_type="create",
        target_memory=proposal["memory_id"],
        loop_id=loop_id,
        payload={**proposal, "proposed": True, "source_hash": f"hash-{loop_id}", "task_id": "T1"},
    )
    run_learning(store=store)
    return proposal


def _pending_review(store):
    return [
        r["review_id"]
        for r in list_reviews(store=store, status="pending")
        if r["proposed_change"]["kind"] == "create"
    ][0]


# ── step 5/9: the gate publishes, after the store is written, and never instead of it ──
def test_an_approved_lesson_is_handed_to_the_notes_after_the_row_is_written(fake_cli, vault, store):
    proposal = _proposal_candidate(store)

    result = approve_review(_pending_review(store), store=store)

    assert result["promotion"]["status"] == "created"
    assert result["basic_memory"]["status"] == "written", result["basic_memory"]
    notes = sorted((vault / "agent-os").glob("*.md"))
    assert [note.name for note in notes] == [f"{proposal['memory_id']}.md"]
    assert store.get_memory(proposal["memory_id"])["status"] == "active", "the store stays authoritative"


def test_the_note_carries_the_words_the_reviewer_wrote(fake_cli, vault, store):
    _proposal_candidate(store)
    approve_review(
        _pending_review(store),
        store=store,
        body="不要按配置名取缓存键，因为它会被两个项目各自解析一遍；用解析后的真实路径。",
        when_to_apply="新增缓存层或改配置解析顺序时",
        tags=["缓存", "配置"],
    )
    note = next((vault / "agent-os").glob("*.md")).read_text(encoding="utf-8")
    assert "不要按配置名取缓存键" in note, "the lesson a human wrote is what the human gets back"
    assert "## 适用" in note and "新增缓存层或改配置解析顺序时" in note
    calls = [json.loads(line) for line in fake_cli.read_text(encoding="utf-8").splitlines()]
    tags = [calls[0]["argv"][i + 1] for i, t in enumerate(calls[0]["argv"]) if t == "--tags"]
    assert sorted(tags) == sorted(["缓存", "配置"]), "the subject the human named travels with the note"


def test_a_failed_publish_leaves_the_approval_and_the_row_intact(fake_cli, vault, store, monkeypatch):
    monkeypatch.setenv("AOS_FAKE_BM_MODE", "crash")
    proposal = _proposal_candidate(store)

    result = approve_review(_pending_review(store), store=store)

    assert result["status"] == "approved"
    assert result["basic_memory"]["status"] == "failed"
    memory = store.get_memory(proposal["memory_id"])
    assert memory and memory["status"] == "active", "a neighbour that will not write cannot un-approve a lesson"
    events = store.list_events(event_type="learning.bm_write_failed")
    assert len(events) == 1
    payload = json.dumps(events[0], ensure_ascii=False)
    assert "缓存键碰撞" not in payload, "the event records that it broke, not what the lesson said"


def test_a_declined_publish_still_approves_and_spawns_nothing(fake_cli, vault, store):
    proposal = _proposal_candidate(store)

    result = approve_review(_pending_review(store), store=store, publish=False)

    assert result["status"] == "approved"
    assert result["basic_memory"]["status"] == "skipped"
    assert store.get_memory(proposal["memory_id"])["status"] == "active"
    assert not fake_cli.exists()


def test_nothing_is_published_when_no_new_row_was_created(fake_cli, vault, store):
    """Only an approval that produced a lesson has a lesson to hand out."""
    _proposal_candidate(store)
    review_id = _pending_review(store)
    approve_review(review_id, store=store)
    calls_before = len(fake_cli.read_text(encoding="utf-8").splitlines())

    again = approve_review(review_id, store=store)

    assert again["status"] == "already_decided"
    assert len(fake_cli.read_text(encoding="utf-8").splitlines()) == calls_before, "no second publish for one decision"


def test_a_resolved_conflict_publishes_the_row_it_created(fake_cli, vault, store):
    from aos.core.memory import evolve, record

    store.upsert_memory(
        {
            "memory_id": "M-A",
            "type": "failure",
            "category": "bugfix",
            "title": "未归一化的输入不要直接拼 cache key，会引发键碰撞",
            "body": "曾回滚两天。",
            "status": "active",
            "scope": "project:warehouse",
            "evidence_level": "runtime_validated",
            "confidence": "high",
            "when_to_apply": "改动缓存 key 之前",
            "lane": "standard",
        },
        tags=["cache", "key"],
    )
    proposal = {
        "memory_id": "M-NEW1",
        "type": "failure",
        "category": "bugfix",
        "title": "cache key 需要归一化，否则会引发键碰撞",
        "body": "曾回滚两天。",
        "scope": "project:warehouse",
        "tags": ["cache", "key"],
        "when_to_apply": "新增缓存 key 时",
        "loop_id": "L9",
        "cwd": "/home/dev/repos/warehouse",
    }
    record.record_outcome(
        loop_id="L9",
        outcome="failure",
        quality_score=0.0,
        memories_used=[],
        needs_review=False,
        source_hash="hash-L9",
        proposal=proposal,
        store=store,
    )
    evolve.run_learning(store=store)
    conflict = [r for r in evolve.list_reviews(store=store, status="pending") if r["kind"] == "conflict"][0]

    result = approve_review(conflict["review_id"], store=store)

    assert result["promotion"]["status"] == "created"
    assert result["basic_memory"]["status"] == "written", result["basic_memory"]
    assert (vault / "agent-os" / "M-NEW1.md").is_file()


def test_a_publish_helper_survives_a_store_that_cannot_read_the_row_back(fake_cli, vault, store, monkeypatch):
    """The publish step is a side effect: even our own bookkeeping failing may not reach the gate."""
    monkeypatch.setattr(MemoryStore, "memories_for_scoring", lambda self, **_k: [])
    _proposal_candidate(store)

    result = approve_review(_pending_review(store), store=store)

    assert result["status"] == "approved"
    assert result["basic_memory"]["status"] == "skipped"
    assert not fake_cli.exists()



# ── the neighbour stays a neighbour: publishing never touches its index ────────
def test_the_engine_never_opens_the_vault_or_the_db_for_writing(fake_cli, vault, tmp_path, monkeypatch):
    source = Path(external_write.__file__).read_text(encoding="utf-8")
    executable = re.sub(r'""".*?"""', "", source, flags=re.S)
    assert "sqlite3" not in executable, "publishing is a CLI call, not a database write"
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|ATTACH|VACUUM)\b", executable, re.I), (
        "the neighbour's index is never ours to modify"
    )
    db = tmp_path / "neighbour.db"
    db.write_bytes(b"not really sqlite, but bytes we must not move")
    monkeypatch.setenv("AOS_BM_DB", str(db))
    before = db.read_bytes()

    result = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=10)

    assert result["status"] == "written"
    assert db.read_bytes() == before
    assert "neighbour.db" not in " ".join(result["argv"])


# ── step 10: the command line stays machine-readable while it says this out loud ──
def test_the_cli_publishes_and_still_prints_one_json_document(capsys, fake_cli, vault, store):
    from aos.cli.main import main

    proposal = _proposal_candidate(store)
    review_id = _pending_review(store)

    assert main(["review", "approve", str(review_id)]) == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["promotion"]["status"] == "created"
    assert emitted["basic_memory"]["status"] == "written"
    assert (vault / "agent-os" / f"{proposal['memory_id']}.md").is_file()


def test_a_failed_publish_says_so_on_stderr_and_still_exits_zero(capsys, fake_cli, vault, store, monkeypatch):
    """A neighbour that will not write must not become a failed approval, and must not hide."""
    from aos.cli.main import main

    monkeypatch.setenv("AOS_FAKE_BM_MODE", "crash")
    proposal = _proposal_candidate(store)
    review_id = _pending_review(store)

    assert main(["review", "approve", str(review_id)]) == 0

    captured = capsys.readouterr()
    emitted = json.loads(captured.out)
    assert emitted["basic_memory"]["status"] == "failed"
    assert "basic-memory" in captured.err, "the human must learn the copy was not made without parsing stdout"
    assert store.get_memory(proposal["memory_id"])["status"] == "active"


def test_the_declination_flag_reaches_the_gate_and_spawns_nothing(capsys, fake_cli, vault, store):
    from aos.cli.main import main

    proposal = _proposal_candidate(store)
    review_id = _pending_review(store)

    assert main(["review", "approve", str(review_id), "--no-publish"]) == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["status"] == "approved"
    assert emitted["basic_memory"]["status"] == "skipped"
    assert not fake_cli.exists()
    assert not (vault / "agent-os").exists()


def test_the_declination_flag_is_discoverable_where_a_person_would_look(capsys):
    """`--help` is the door: a flag that only exists in the source is a flag nobody has."""
    from aos.cli.main import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["review", "approve", "--help"])

    help_text = capsys.readouterr().out
    assert "--no-publish" in help_text, help_text
    assert "basic-memory" in help_text, "the help must say what is being declined"


# ── the isolation that keeps a test out of the owner's notebook ────────────────
def test_the_hermetic_default_hands_nothing_even_to_a_working_command(tmp_path, monkeypatch):
    """`AOS_BM_CONFIG_DIR` in conftest is the whole reason `approve` in a test cannot write a note.

    Left as the default (a directory with no `config.json`), the vault is unresolvable
    and publishing declines **before** it would have spent a spawn. The command here
    works on purpose: if the guard were the missing binary, this would pass for the
    wrong reason.
    """
    script = tmp_path / "bm.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AOS_BM_BIN", f"{sys.executable} {script}")
    monkeypatch.setenv("AOS_FAKE_BM_LOG", str(log))
    monkeypatch.setenv("AOS_FAKE_BM_VAULT", str(tmp_path / "vault"))

    result = external_write.publish_lesson(memory_row(), tags=["pytest"], review_id=1, authored_by="owner", timeout=5)

    assert result["status"] == "skipped", result
    assert not log.exists(), "nothing was asked of the neighbour"
