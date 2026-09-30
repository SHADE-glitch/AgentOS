"""The ``aos`` command line entry point.

Phase 1 provides ``--version`` and ``doctor``. The preflight/postflight
commands already speak the frozen contract (falling back fail-open until
the core lifecycle is ported); the remaining commands are wired in later
phases.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from aos import __version__
from aos.config import ConfigError, get_paths
from aos.contract import CONTRACT_VERSION, ValidationError, fallback_postflight, fallback_preflight, validate_postflight, validate_preflight

NOT_IMPLEMENTED = 2


# ── Helpers ────────────────────────────────────────────────────────────
def _read_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Read the JSON request payload from --payload or stdin."""
    if args.payload_stdin:
        raw = sys.stdin.read()
    elif args.payload:
        raw = args.payload
    else:
        raise SystemExit("error: one of --payload or --payload-stdin is required")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("error: payload must be a JSON object")
    return data


def _load_lifecycle():
    """Return the core lifecycle module, or None if not yet ported."""
    try:
        from aos.core.loop import lifecycle  # type: ignore
    except ImportError:
        return None
    return lifecycle


def _emit(doc: dict[str, Any]) -> None:
    print(json.dumps(doc, ensure_ascii=False, sort_keys=False))


# ── Commands ───────────────────────────────────────────────────────────
def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        paths = get_paths()
    except ConfigError as exc:
        print(f"Agent OS Doctor\n  [FAIL] {exc}")
        return 1

    print("Agent OS Doctor")
    print(f"  version:         {__version__}")
    print(f"  contract:        {CONTRACT_VERSION}")
    print(f"  root:            {paths.root}")
    print(f"  store:           {paths.store_dir} {'[OK]' if paths.store_dir.is_dir() else '[MISSING]'}")
    print(f"  database:        {paths.db_path} {'[OK]' if paths.db_path.is_file() else '[ABSENT]'}")
    print(f"  content:         {paths.content_dir} {'[OK]' if paths.content_dir.is_dir() else '[MISSING]'}")
    print(f"  policies:        {paths.policies_dir} {'[OK]' if paths.policies_dir.is_dir() else '[MISSING]'}")

    lifecycle = _load_lifecycle()
    print(f"  core lifecycle:  {'[OK]' if lifecycle else '[NOT PORTED]'}")
    print()
    print(f"Status: {'READY' if lifecycle else 'FOUNDATION ONLY'}")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    payload = _read_payload(args)
    lifecycle = _load_lifecycle()
    if lifecycle is None:
        doc = fallback_preflight("core lifecycle not yet ported", task_id=payload.get("task_id", ""), session_id=payload.get("session_id", ""))
    else:
        doc = lifecycle.preflight(
            task=payload.get("task", ""),
            session_id=payload.get("session_id", ""),
            cwd=payload.get("cwd", ""),
            memory_mode=payload.get("memory_mode", "enabled"),
            provider=payload.get("provider", "opencode"),
            model=payload.get("model", ""),
        )
    validate_preflight(doc)
    _emit(doc)
    return 0


def cmd_postflight(args: argparse.Namespace) -> int:
    payload = _read_payload(args)
    lifecycle = _load_lifecycle()
    if lifecycle is None:
        doc = fallback_postflight("core lifecycle not yet ported", task_id=payload.get("task_id", ""), loop_id=payload.get("loop_id", ""), session_id=payload.get("session_id", ""))
    else:
        doc = lifecycle.postflight(
            task_id=payload.get("task_id", ""),
            loop_id=payload.get("loop_id", ""),
            session_id=payload.get("session_id", ""),
            cwd=payload.get("cwd", ""),
        )
    validate_postflight(doc)
    _emit(doc)
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    try:
        from aos.core.routing.router import route_task
    except ImportError:
        print("error: routing core not yet ported", file=sys.stderr)
        return NOT_IMPLEMENTED
    decision = route_task(args.task)
    _emit(decision)
    return 0


def _not_implemented(name: str, phase: str) -> int:
    print(f"error: `aos {name}` is not implemented yet ({phase})", file=sys.stderr)
    return NOT_IMPLEMENTED


def cmd_run(args: argparse.Namespace) -> int:
    return _not_implemented("run", "phase 5")


def cmd_memory(args: argparse.Namespace) -> int:
    return _not_implemented("memory", "phase 3")


def cmd_review(args: argparse.Namespace) -> int:
    return _not_implemented("review", "phase 4")


# ── Parser ─────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aos",
        description="Agent OS — routing, memory and evolution for coding agents",
    )
    parser.add_argument("--version", action="store_true", help="show version and exit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="diagnose the Agent OS environment")

    for phase in ("preflight", "postflight"):
        p = sub.add_parser(phase, help=f"run the {phase} contract for a host")
        p.add_argument("--payload", help="JSON request payload")
        p.add_argument("--payload-stdin", action="store_true", help="read the JSON payload from stdin")

    p_route = sub.add_parser("route", help="classify and route a task (debug)")
    p_route.add_argument("task", help="task text")

    p_run = sub.add_parser("run", help="run a task through the full lifecycle")
    p_run.add_argument("task", help="task text")
    p_run.add_argument("--cwd", default="", help="working directory (default: current directory)")
    p_run.add_argument("--memory", choices=["on", "off"], default="on")
    p_run.add_argument("--provider", default="opencode")
    p_run.add_argument("--model", default="")

    sub.add_parser("memory", help="inspect the memory store")
    sub.add_parser("review", help="review pending memory promotions")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"aos {__version__}")
        return 0

    handlers = {
        "doctor": cmd_doctor,
        "preflight": cmd_preflight,
        "postflight": cmd_postflight,
        "route": cmd_route,
        "run": cmd_run,
        "memory": cmd_memory,
        "review": cmd_review,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
