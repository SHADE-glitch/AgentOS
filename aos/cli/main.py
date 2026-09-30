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


def cmd_run(args: argparse.Namespace) -> int:
    from aos.core.loop import lifecycle

    doc = lifecycle.run(
        task=args.task,
        cwd=args.cwd,
        provider=args.provider,
        model=args.model,
        memory_mode="enabled" if args.memory == "on" else "disabled",
        test_command=args.test_command,
        test_exit_code=args.test_exit_code,
    )
    validate_postflight(doc)
    _emit(doc)
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    from aos.core.memory.store import MemoryStore

    command = getattr(args, "memory_command", None)
    if command != "list":
        print("usage: aos memory list [--type TYPE]", file=sys.stderr)
        return 1

    store = MemoryStore()
    try:
        memories = store.list_memories(type=getattr(args, "type", None))
        if not memories:
            print("(no memories)")
            return 0
        for m in memories:
            print(f"{m['memory_id']:<12} {m['type']:<14} {m['category']:<14} decay={m['decay_factor']:<5} {m['title']}")
        print(f"\n{len(memories)} memories")
        return 0
    finally:
        store.close()


def cmd_review(args: argparse.Namespace) -> int:
    from aos.core.memory import evolve

    command = getattr(args, "review_command", None) or "list"

    if command == "list":
        reviews = evolve.list_reviews(status=getattr(args, "status", None))
        if not reviews:
            print("(no reviews)")
            return 0
        for review in reviews:
            evidence = review["evidence"]
            reason = evidence.get("reason") or ""
            print(
                f"#{review['review_id']:<4} {review['status']:<9} {review['memory_id']:<12} "
                f"runs={evidence.get('validation_runs', 0)} quality={evidence.get('quality_score', 0)} {reason}"
            )
        print(f"\n{len(reviews)} reviews")
        return 0

    if command in ("approve", "reject"):
        if command == "approve":
            result = evolve.approve_review(args.review_id)
            expected = "approved"
        else:
            result = evolve.reject_review(args.review_id)
            expected = "rejected"
        _emit(result)
        return 0 if result["status"] == expected else 1

    print("usage: aos review list [--status STATUS] | approve <id> | reject <id>", file=sys.stderr)
    return 1


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
    p_run.add_argument("--test-command", default="", help="test command to record as evidence")
    p_run.add_argument("--test-exit-code", type=int, default=None, help="test exit code (0 = pass)")

    p_memory = sub.add_parser("memory", help="inspect the memory store")
    mem_sub = p_memory.add_subparsers(dest="memory_command")
    p_mem_list = mem_sub.add_parser("list", help="list memories")
    p_mem_list.add_argument("--type", default=None, help="filter by memory type")

    p_review = sub.add_parser("review", help="review pending memory promotions")
    review_sub = p_review.add_subparsers(dest="review_command")
    p_review_list = review_sub.add_parser("list", help="list learning reviews")
    p_review_list.add_argument(
        "--status", choices=["pending", "approved", "rejected"], default=None, help="filter by status"
    )
    for action in ("approve", "reject"):
        p_action = review_sub.add_parser(action, help=f"{action} a pending review")
        p_action.add_argument("review_id", type=int, help="review id")

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
