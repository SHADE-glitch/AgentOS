"""Publish one approved lesson into basic-memory — one way, through its own CLI.

The human gate is the only place a lesson becomes durable, and for two weeks the
durable thing was a row in ``store/`` that nothing but the engine reads. This
module gives the same lesson to the notes a human actually edits, so "what Agent OS
learned" appears on the owner's work surface instead of only in a table.

Three constraints hold it in place, and each is enforced in code rather than in a
comment:

* **the neighbour's database is never ours to write.** Recall reads it read-only
  (:mod:`aos.core.memory.external`); this module never opens it at all. The only
  door is ``basic-memory tool write-note`` — the neighbour's own command line, with
  ``--local`` so the write cannot be routed to a cloud it has no credentials for.
* **the store stays authoritative.** Callers write the row, the review status and
  the event *first*; a publish that fails afterwards is a reported side effect, not
  a rolled-back decision. Nothing here raises into the gate.
* **one memory is one note.** The filename is the stable ``memory_id``, so a second
  approval of the same lesson updates that file instead of writing a second copy —
  and a file that does not carry our marker is somebody else's note and is refused.

The content travels on stdin, never in argv: it is text a model produced, and
putting it in the argument list would make the note's own body an injection vector
for option parsing.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from aos.config import basic_memory_bin, basic_memory_config_dir
from aos.core.memory.policy import load_policy

# Every option this engine is allowed to hand the neighbour's CLI. Anything else —
# `--cloud` especially — is refused before a process is spawned.
WRITABLE_FLAGS = frozenset(
    {
        "--title",
        "--folder",
        "--content",
        "--tags",
        "--type",
        "--project",
        "--project-id",
        "--overwrite",
        "--local",
    }
)

SUBCOMMANDS = ("tool", "write-note")

# A memory body is model output, so it may contain a fence or an ownership key.
# Replaced with a marker rather than deleted: a reader of the note can see that the
# lesson contained something that had to be neutralised, which is not the same claim
# as "nothing was dropped" (the same choice `inject.py` makes for boundary tags).
_REMOVED = "[已移除]"
_FENCE = re.compile(r"^\s*-{3,}\s*$")
_OWNERSHIP_KEY = re.compile(r"^\s*(?:agent_os|aos_[a-z_]+)\s*:", re.I)
# A memory id is the filename, so it may not be able to escape the folder.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_OURS = re.compile(r"^agent_os:\s*true\s*$", re.MULTILINE)
_HEAD_BYTES = 4096


def _scalar(value: Any) -> str:
    """Render one frontmatter value as JSON, which is valid YAML for scalars.

    Quoting is the whole defence here: a value containing ``: ``, a leading ``[``,
    or a quote cannot then re-shape the block it is written into.
    """
    if value is None:
        value = ""
    if isinstance(value, (int, float, bool)):
        return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def _clean(text: Any) -> str:
    """Neutralise fences and ownership keys in model-authored text, line by line."""
    lines = []
    for line in str(text or "").splitlines():
        if _FENCE.match(line) or _OWNERSHIP_KEY.match(line):
            lines.append(_REMOVED)
        else:
            lines.append(line)
    return "\n".join(lines)


def build_note(memory: Mapping[str, Any], *, review_id: Any, authored_by: Any) -> tuple[str, str, list[str]]:
    """Return ``(title, content, tags)`` for one memory — pure, spawns nothing.

    ``title`` is the memory id because it becomes the filename; the human-readable
    title goes inside as the H1, where a person reads it and nothing keys off it.
    """
    memory_id = str(memory.get("memory_id") or "")
    tags = [str(tag) for tag in (memory.get("tags") or []) if str(tag).strip()]
    when = _clean(memory.get("when_to_apply") or "")
    body = _clean(memory.get("body") or memory.get("title") or "")

    fields = [
        ("agent_os", True),
        ("aos_schema", 1),
        ("aos_memory_id", memory_id),
        ("aos_type", memory.get("type") or ""),
        ("aos_evidence_level", memory.get("evidence_level") or ""),
        ("aos_confidence", memory.get("confidence") if memory.get("confidence") is not None else ""),
        ("aos_status", memory.get("status") or ""),
        ("aos_lane", memory.get("lane") or ""),
        ("aos_scope", memory.get("scope") or "global"),
        ("aos_when_to_apply", when),
        ("aos_dedupe_key", memory.get("dedupe_key") or ""),
        ("aos_source_loop_id", memory.get("source_loop_id") or ""),
        ("aos_source_task", memory.get("source_task") or ""),
        ("aos_source_project", memory.get("source_project") or ""),
        ("aos_review_id", review_id),
        ("aos_authored_by", authored_by),
    ]
    block = "\n".join(f"{key}: {_scalar(value)}" for key, value in fields)

    provenance = [
        f"- 评审 #{review_id}，批准人 {authored_by or '未记名'}",
        f"- 来源：loop {memory.get('source_loop_id') or '未记'}"
        f" / task {memory.get('source_task') or '未记'}"
        f" / 项目 {memory.get('source_project') or '未记'}",
        f"- 证据等级 {memory.get('evidence_level') or '未记'}"
        f"，置信 {memory.get('confidence') if memory.get('confidence') is not None else '未记'}"
        f"，通道 {memory.get('lane') or '未记'}，作用域 {memory.get('scope') or 'global'}",
        "- 这一篇由 Agent OS 在人门批准时写出；之后的编辑归人，引擎不会再来覆盖自己的标记。",
    ]

    content = "\n".join(
        [
            "---",
            block,
            "---",
            "",
            f"# {memory.get('title') or memory_id}",
            "",
            body,
            "",
            "## 适用",
            "",
            when or "（批准时没有写下适用条件。）",
            "",
            "## 证据",
            "",
            *provenance,
            "",
        ]
    )
    return memory_id, content, tags


def vault_root() -> Optional[Path]:
    """The neighbour's vault, read out of its own ``config.json`` — or ``None``.

    The path is a value inside somebody else's file, so it is looked up rather than
    configured: a second copy here is exactly the drift this repository keeps being
    burned by. Anything missing or malformed returns ``None``, which the caller
    turns into ``skipped`` — never an exception, and never a guessed location.
    """
    config = basic_memory_config_dir() / "config.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return None
    name = data.get("default_project") or ""
    project = projects.get(name)
    if not isinstance(project, dict):
        return None
    path = project.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    return Path(path).expanduser()


def note_path(memory_id: str, *, folder: str) -> Optional[Path]:
    """Where this memory's note lives, or ``None`` if it cannot be answered safely."""
    if not _SAFE_ID.match(str(memory_id or "")):
        return None
    root = vault_root()
    if root is None or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", str(folder or "")):
        return None
    return root / folder / f"{memory_id}.md"


def ownership_of(path: Optional[Path]) -> str:
    """``ours`` / ``foreign`` / ``absent`` — read-only, and the reason it is checked first."""
    if path is None:
        return "absent"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(_HEAD_BYTES)
    except FileNotFoundError:
        return "absent"
    except OSError:
        # Unreadable is not "absent": claiming a file we cannot see would let a
        # write proceed over something we did not verify.
        return "foreign"
    return "ours" if _OURS.search(head) else "foreign"


def _refuse(values: Sequence[str]) -> Optional[str]:
    """Reject any value that could be read back as an option."""
    for value in values:
        text = str(value)
        if text.startswith("-"):
            return f"refused: {text!r} would be parsed as an option"
        if "\x00" in text or "\n" in text:
            return f"refused: {text[:20]!r} is not a single-line value"
    return None


def _command(*, title: str, folder: str, tags: Sequence[str], project: str) -> list[str]:
    argv = ["tool", "write-note", "--title", title, "--folder", folder, "--type", "note", "--overwrite", "--local"]
    if project:
        argv += ["--project", project]
    for tag in tags:
        argv += ["--tags", tag]
    offending = [token for token in argv if token.startswith("--") and token not in WRITABLE_FLAGS]
    if offending:
        raise ValueError(f"flag outside the write whitelist: {offending[0]}")
    return argv


def _run_write(
    prefix: str,
    *,
    title: str,
    folder: str,
    content: str,
    tags: Sequence[str],
    project: str,
    timeout: float,
) -> dict[str, Any]:
    """Spawn the neighbour's CLI with the note on stdin. Never raises; reports."""
    argv = shlex.split(prefix) + _command(title=title, folder=folder, tags=tags, project=project)
    if not argv[:1]:
        return {"argv": argv, "returncode": -1, "stdout": "", "stderr": "", "error": "empty command prefix"}
    try:
        completed = subprocess.run(
            argv,
            input=content,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "argv": argv,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"timed out after {timeout}s",
        }
    except (OSError, ValueError) as exc:
        # A missing `uvx`, a bad prefix, an unfriendly sandbox — all of them are the
        # neighbour being unavailable, which is a reported side effect, not a crash.
        return {"argv": argv, "returncode": -1, "stdout": "", "stderr": "", "error": str(exc)}
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "error": "",
    }


def _published_fields(stdout: str) -> tuple[str, str]:
    """``(permalink, file_path)`` out of the neighbour's reply, or blanks.

    The neighbour answers with **pretty-printed** JSON, so the whole payload is
    parsed first and only then a brace-delimited slice of it — reading the last line
    alone silently returned ``""`` on the first real run, which is exactly the
    "declared but nobody reads it" shape this repository keeps meeting.
    The reply is somebody else's format, so a shape we do not recognise yields
    empty strings rather than a guess; the write already happened either way.
    """
    text = (stdout or "").strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return str(data.get("permalink") or ""), str(data.get("file_path") or "")
    return "", ""


def _result(
    status: str,
    *,
    permalink: str = "",
    file_path: str = "",
    error: str = "",
    argv: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "permalink": permalink,
        "file_path": file_path,
        "error": error,
        "argv": list(argv or []),
    }


def publish_lesson(
    memory: Mapping[str, Any],
    *,
    tags: Sequence[str] = (),
    review_id: Any = "",
    authored_by: Any = "",
    timeout: Optional[float] = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Write one approved lesson into the neighbour's notes. Cannot raise, never blocks the gate.

    Returns ``{status, permalink, file_path, error, argv}`` with ``status`` in
    ``written|disabled|failed|skipped|conflict``. ``disabled`` and ``skipped`` are
    decisions, not failures: the first is the off-switch, the second is a vault that
    is not there to write into. ``conflict`` means a note exists that does not carry
    our marker — a human wrote it, and Agent OS does not own it.
    """
    try:
        rules = load_policy("external_write")
        if not publish:
            return _result("skipped", error="publishing declined by the caller (--no-publish)")
        if not rules.get("enabled") or not basic_memory_bin():
            return _result("disabled", error="publishing is switched off")

        supplied = [str(tag) for tag in tags if str(tag).strip()]
        row = dict(memory)
        if supplied:
            row["tags"] = supplied
        title, content, note_tags = build_note(row, review_id=review_id, authored_by=authored_by)
        if not title:
            return _result("skipped", error="the row carries no memory_id to name the note")

        folder = str(rules.get("folder") or "agent-os")
        project = str(rules.get("project") or "")
        limit = float(timeout if timeout is not None else rules.get("timeout_seconds", 30))

        path = note_path(title, folder=folder)
        if path is None:
            return _result("skipped", error="the neighbour's vault could not be resolved from its own config")
        owner = ownership_of(path)
        if owner == "foreign":
            return _result("conflict", file_path=str(path), error="a note exists there that Agent OS does not own")

        refused = _refuse([title, folder, project, *note_tags])
        if refused:
            return _result("failed", error=refused)

        outcome = _run_write(
            basic_memory_bin(),
            title=title,
            folder=folder,
            content=content,
            tags=note_tags,
            project=project,
            timeout=limit,
        )
        argv, file_str = outcome["argv"], str(path)
        if outcome["returncode"] == 0:
            permalink, published_path = _published_fields(str(outcome["stdout"]))
            return _result(
                "written",
                permalink=permalink,
                file_path=published_path or file_str,
                error=str(outcome["stderr"])[:200] if outcome["stderr"] else "",
                argv=argv,
            )
        if "NOTE_ALREADY_EXISTS" in str(outcome["stderr"]) + str(outcome["stdout"]):
            return _result("conflict", file_path=file_str, error="the neighbour refused to overwrite", argv=argv)
        detail = str(outcome["stderr"] or outcome["error"] or outcome["stdout"]).strip()
        return _result("failed", file_path=file_str, error=detail[:200] or f"exit {outcome['returncode']}", argv=argv)
    except Exception as exc:  # noqa: BLE001 — the gate must survive anything said here
        return _result("failed", error=f"publish gave up: {exc}")
