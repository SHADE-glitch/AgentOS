#!/usr/bin/env python3
"""Measurement-only friction oracle for the live rig.

Why this file exists
-------------------
Stage 0's first exit criterion asks whether a project produced real friction — a
failed attempt, a repair, a re-verification. exp-v1's own `tool_trace` cannot answer
that: `ok` comes from the exit number the host attaches to a *whole* shell invocation,
so `pytest | tail` reports `tail`'s zero and `cp x && pytest && git diff` reports the
last command's. Measured on LGD-02: 19 bash calls, 18 of them compound, two genuine
test failures, and zero `ok=false` in the trace.

So the oracle reads the host's own session database and states what the host recorded.
It is an instrument, not a capability:

  * it opens the host database read-only and never writes;
  * it never talks to the engine, the store, the memory table or the review queue;
  * its output is never put in a prompt and never reaches the model;
  * absence of a signal is reported as absence, never as success.

A second command-name normaliser lives here on purpose. Reusing the plugin's would
make the instrument grade itself: the oracle exists to disagree with `tool_trace`.
It differs where the plugin is known to be wrong (defect AN): every shell segment of
a call is named, not just the first one.

Privacy line: the host's command text and tool output are read here and thrown away.
What leaves this file is a name-shaped class list, integers and digests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "aos-friction-oracle/1"

VERDICT_SUCCESS = "success"
VERDICT_FAILURE = "failure"
VERDICT_UNKNOWN = "unknown"

# Words that introduce a command instead of being one.
NOISE = {"cd", "env", "export", "sudo", "time", "nohup", "source", "set", "echo"}
INTERPRETERS = {"python", "python2", "python3", "node", "deno", "bun", "php", "ruby"}
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,23}$")
SEGMENT = re.compile(r"&&|\|\||[;|\n]")
MAX_CLASS_TOKENS = 3

# A test command is a command whose *purpose* is to run tests. Anything else is None:
# an unrecognised command is not a passing test.
TEST_COMMANDS = {
    "pytest": re.compile(r"\bpytest\b"),
    "unittest": re.compile(r"(?:^|\s)-m\s+unittest\b"),
    "go_test": re.compile(r"\bgo\s+test\b"),
    "cargo_test": re.compile(r"\bcargo\s+test\b"),
    "ctest": re.compile(r"\bctest\b"),
    "npm_test": re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+test\b"),
    "make_test": re.compile(r"\bmake\s+test\b"),
}

# Only the pytest summary line is parsed for counts, because that is the one this
# experiment project emits. Other runners: `observed_test_results` stays None, which
# means "not parsed" and must never be read as "nothing failed".
PYTEST_COUNTS = {
    "failed": re.compile(r"\b(\d+) failed\b"),
    "passed": re.compile(r"\b(\d+) passed\b"),
    "errors": re.compile(r"\b(\d+) errors?\b"),
}
# One pytest run ends with `... in 1.44s`. A compound call can hold two of them — the
# break and the repair — so the output is cut at every marker instead of read once.
PYTEST_RUN_END = re.compile(r"in \d+(?:\.\d+)?s")

DEFAULT_HOST_DB = Path.home() / ".local/share/opencode/opencode.db"


def command_classes(command: str) -> list[str]:
    """One name-shaped class per shell segment, values and paths removed."""
    classes: list[str] = []
    for segment in SEGMENT.split(command or ""):
        kept: list[str] = []
        for token in segment.split():
            if token == "-m" and kept and kept[-1] in INTERPRETERS:
                kept.append(token)
                continue
            if NAME.match(token) and token not in NOISE:
                kept.append(token)
                if len([entry for entry in kept if entry != "-m"]) >= MAX_CLASS_TOKENS:
                    break
        if kept:
            classes.append(" ".join(kept))
    return classes[:8]


def test_command_of(classes: list[str]) -> str | None:
    joined = "; ".join(classes)
    for name, pattern in TEST_COMMANDS.items():
        if pattern.search(joined):
            return name
    return None


def observed_test_results(classes: list[str], output: str) -> list[dict] | None:
    """Per pytest run, the counts the host recorded — or None when nothing was parsed.

    One shell call can carry two runs (break the fix, see red, restore, see green), so
    this returns a list. None means "not parsed"; it is never a zero.
    """
    if test_command_of(classes) != "pytest":
        return None
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    windows: list[str] = []
    start = 0
    for match in PYTEST_RUN_END.finditer(text):
        windows.append(text[start:match.end()])
        start = match.end()
    if not windows:
        windows = [text]
    parsed = []
    for window in windows:
        found = {key: int(match.group(1)) for key, pattern in PYTEST_COUNTS.items()
                 if (match := pattern.search(window))}
        if found:
            parsed.append({"failed": found.get("failed", 0), "passed": found.get("passed", 0),
                           "errors": found.get("errors", 0)})
    return parsed or None


def verdict_of(exit_code: object, status: str) -> str:
    """`unknown` is a real answer: no exit number is not a passing command."""
    if status and status not in ("completed", "running", "pending"):
        return VERDICT_FAILURE
    if isinstance(exit_code, bool):
        return VERDICT_UNKNOWN
    if isinstance(exit_code, int):
        return VERDICT_SUCCESS if exit_code == 0 else VERDICT_FAILURE
    return VERDICT_UNKNOWN


def connect_host_readonly(path: Path | str) -> sqlite3.Connection:
    """An sqlite handle that cannot write, and cannot create a database by accident."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"host database not found: {target}")
    return sqlite3.connect(f"file:{target}?mode=ro", uri=True)


def host_steps(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "select tool, status, exit, command, output from ("
        "  select json_extract(data,'$.tool') as tool,"
        "         json_extract(data,'$.state.status') as status,"
        "         json_extract(data,'$.state.metadata.exit') as exit,"
        "         json_extract(data,'$.state.input.command') as command,"
        "         json_extract(data,'$.state.output') as output,"
        "         time_created, id"
        "  from part where session_id = ? and json_extract(data,'$.type') = 'tool'"
        "  order by time_created, id)",
        (session_id,),
    ).fetchall()
    steps: list[dict] = []
    for index, (tool, status, exit_code, command, output) in enumerate(rows, start=1):
        classes = command_classes(command or "")
        steps.append({
            "seq": index,
            "tool": tool or "-",
            "status": status or "",
            "exit": exit_code if isinstance(exit_code, int) else None,
            "verdict": verdict_of(exit_code, status or ""),
            "command_classes": classes,
            "test_command": test_command_of(classes),
            "observed_test_results": observed_test_results(classes, output or ""),
        })
    return steps


def masked_test_failures(steps: list[dict]) -> list[dict]:
    """Test runs the host recorded as succeeding — the class of event `tool_trace` misses."""
    masked = []
    for step in steps:
        results = step["observed_test_results"]
        if results and any(result["failed"] + result["errors"] for result in results) \
                and step["verdict"] != VERDICT_FAILURE:
            masked.append({"seq": step["seq"], "test_command": step["test_command"],
                           "exit": step["exit"], "observed_test_results": results})
    return masked


def project_state(root: Path | str) -> dict:
    """An independent account of where the project stood: numbers and a digest, no paths."""

    def git(*args: str) -> str:
        # GIT_OPTIONAL_LOCKS=0: `git status` would otherwise refresh the project's index,
        # and an instrument that touches what it measures is not measuring anything.
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return done.stdout.strip() if done.returncode == 0 else ""

    if not git("rev-parse", "--git-dir"):
        return {"is_repo": False}
    porcelain = git("status", "--porcelain=v1")
    entries = [line for line in porcelain.splitlines() if line.strip()]
    return {
        "is_repo": True,
        "head": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "commits": int(git("rev-list", "--count", "HEAD") or 0),
        "dirty_entries": len(entries),
        # A digest so two runs can be compared without naming anybody's files.
        "status_digest": hashlib.sha256("\n".join(sorted(entries)).encode()).hexdigest(),
    }


def build_report(host_db: Path | str, session_id: str, *, project_root: Path | str | None = None) -> dict:
    conn = connect_host_readonly(host_db)
    try:
        steps = host_steps(conn, session_id)
    finally:
        conn.close()
    counts = {"tool_parts": len(steps)}
    for verdict in (VERDICT_SUCCESS, VERDICT_FAILURE, VERDICT_UNKNOWN):
        counts[verdict] = sum(1 for step in steps if step["verdict"] == verdict)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measurement_only": "read by the operator only; never given to the model, never sent to the engine",
        "host_session": {
            "database": Path(host_db).name,
            "session_id": session_id,
            "steps": steps,
            "counts": counts,
            "masked_test_failures": masked_test_failures(steps),
        },
        "project": project_state(project_root) if project_root else None,
    }


def find_sessions(log: Path) -> list[str]:
    """Session ids the host itself printed, most-used first — no engine data involved."""
    text = log.read_text(encoding="utf-8", errors="replace")
    seen: dict[str, int] = {}
    for session in re.findall(r"session\.id=(ses_[A-Za-z0-9]+)", text):
        seen[session] = seen.get(session, 0) + 1
    return [key for key, _ in sorted(seen.items(), key=lambda item: (-item[1], item[0]))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="friction_oracle.py", description="read-only friction oracle")
    parser.add_argument("--session", help="host session id; default: the one in --from-log")
    parser.add_argument("--from-log", type=Path, help="rig log to read the session id out of")
    parser.add_argument("--host-db", type=Path, default=DEFAULT_HOST_DB)
    parser.add_argument("--project", type=Path, help="project root to summarise git state for")
    parser.add_argument("--out", type=Path, help="write the JSON report here (default: stdout)")
    args = parser.parse_args(argv)

    session = args.session
    if not session:
        if not args.from_log:
            print("either --session or --from-log is required", file=sys.stderr)
            return 2
        sessions = find_sessions(args.from_log)
        if not sessions:
            print(f"no session id found in {args.from_log}", file=sys.stderr)
            return 2
        session = sessions[0]

    try:
        report = build_report(args.host_db, session, project_root=args.project)
    except (FileNotFoundError, sqlite3.Error) as exc:
        # Say it out loud: an oracle that quietly reports nothing is the AF-shaped failure.
        print(f"oracle could not read the host database: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    counts = report["host_session"]["counts"]
    masked = report["host_session"]["masked_test_failures"]
    print(f"oracle session={session} parts={counts['tool_parts']} "
          f"success={counts[VERDICT_SUCCESS]} failure={counts[VERDICT_FAILURE]} "
          f"unknown={counts[VERDICT_UNKNOWN]} masked_test_failures={len(masked)}"
          + (f" out={args.out}" if args.out else ""))
    if not args.out:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
