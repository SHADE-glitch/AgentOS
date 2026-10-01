"""The ``aos`` command line entry point.

Two kinds of caller use this binary. A host (OpenCode, through its plugin) speaks
the frozen JSON contract on stdin and gets one on stdout — ``preflight`` and
``postflight``, which fail open rather than ever raising into a prompt. A human
speaks argv: ``memory`` authors and inspects the store, ``review`` is the gate
that decides what becomes knowledge, and ``doctor`` reports whether the loop is
healthy. The contract is the only way in for a host; there is no second host
protocol, by design.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from aos import __version__
from aos.config import ConfigError, get_paths
from aos.contract import (
    CONTRACT_VERSION,
    SUPPORTED_VERSIONS,
    collect_signals,
    fallback_postflight,
    fallback_preflight,
    unread_request_fields,
    validate_postflight,
    validate_preflight,
    validate_request,
)

NOT_IMPLEMENTED = 2
BAD_REQUEST = 3


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


def _rejected(doc: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Attach request errors to a fallback document before it goes out."""
    doc["warnings"] = list(doc.get("warnings", [])) + errors
    return doc


def _note_unread(doc: dict[str, Any], payload: dict[str, Any], *, phase: str) -> dict[str, Any]:
    """Tell the caller which fields were ignored instead of dropping them."""
    unread = unread_request_fields(payload, phase=phase)
    if unread:
        doc["warnings"] = list(doc.get("warnings", [])) + [
            f"ignored unknown request field: {key}" for key in unread
        ]
    return doc


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
def _schema_state(db_path) -> dict:
    """The store's schema facts as data, for both the human line and `--json`.

    Diagnosis must not migrate, create, or repair anything: `doctor` is the
    command run when something looks wrong, and a diagnostic that rewrites the
    store is how a diagnosis becomes the incident.
    """
    import sqlite3

    from aos.core.memory import migrations

    state = {
        "expected": migrations.LATEST_VERSION,
        "installed": None,
        "readable": False,
        "present": Path(db_path).is_file(),
        "pending": [],
        "note": "",
    }
    if not state["present"]:
        state["note"] = f"no database yet — will be built at v{migrations.LATEST_VERSION}"
        return state
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        state["note"] = f"unreadable ({exc})"
        return state
    try:
        version = migrations.current_version(conn)
    except sqlite3.Error:
        conn.close()
        state["note"] = "unreadable schema version"
        return state
    conn.close()

    state["installed"] = version
    state["readable"] = True
    if version == 0:
        state["note"] = "unversioned file (pre-migration)"
    elif version < migrations.LATEST_VERSION:
        state["pending"] = [m.describe() for m in migrations.pending_migrations(version)]
        state["note"] = (
            f"v{version} [BEHIND] — the next write runs {', '.join(state['pending'])}; "
            "run `aos memory migrate` to do it now, with a backup"
        )
    elif version > migrations.LATEST_VERSION:
        state["note"] = f"v{version} [NEWER THAN ENGINE v{migrations.LATEST_VERSION}]"
    else:
        state["note"] = f"v{version} ok"
    return state


def _schema_line(db_path) -> str:
    """One line for a human, from the same facts `--json` reports."""
    state = _schema_state(db_path)
    if state["installed"] == state["expected"] and state["readable"]:
        return f"v{state['installed']} [OK]"
    return state["note"]


def _doctor_document(paths) -> dict:
    """The machine-readable form of `doctor` — the plugin's probe before it speaks.

    Kept to facts a host can act on: versions (so a plugin can negotiate before
    it sends anything it might get a version error for), paths, whether the store
    is readable and at which schema, and the queue's shape. No secrets, no memory
    bodies.
    """
    from aos.core.loop import pending as loop_pending
    from aos.core.memory import migrations
    from aos.core.memory.store import MemoryStore

    schema = _schema_state(paths.db_path)
    document = {
        "ok": schema["readable"] or not schema["present"],
        "status": "READY",
        "aos_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "supported_versions": list(SUPPORTED_VERSIONS),
        "schema": {
            "expected": migrations.LATEST_VERSION,
            "installed": schema["installed"],
            "readable": schema["readable"],
            "present": schema["present"],
            "pending": schema["pending"],
        },
        "paths": {
            "root": str(paths.root),
            "store": str(paths.store_dir),
            "database": str(paths.db_path),
            "content": str(paths.content_dir),
            "policies": str(paths.policies_dir),
            "pending_dir": str(paths.pending_dir),
        },
        "features": {"preflight": True, "postflight": True, "memory": True, "learning_gate": True},
    }
    # Loops that opened and never reported back. The directory used to exist with
    # no writer and no reader; now the first is the loop and this is the second.
    document["pending_postflight"] = loop_pending.summary()
    try:
        store = MemoryStore()
    except Exception as exc:  # a store that will not open is a diagnosis, not a crash
        store = None
        document["ok"] = False
        document["status"] = "FAIL"
        document["error"] = f"store unreadable: {exc}"
    if store is not None:
        try:
            rows = store.list_memories()
            by_status: dict = {}
            for row in rows:
                by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            document["memories"] = {
                "total": len(rows),
                "by_status": by_status,
                "recallable": sum(
                    1 for r in rows if r["status"] in ("active", "verified")
                ),
                "without_dedupe_key": sum(1 for r in rows if not r["dedupe_key"]),
            }
            reviews = store.list_reviews(status="pending")
            by_kind: dict = {}
            for review in reviews:
                by_kind[review["kind"]] = by_kind.get(review["kind"], 0) + 1
            document["reviews"] = {"pending": len(reviews), "by_kind": by_kind}
            document["candidates"] = {"open": len(store.list_open_candidates())}
            # Split by source: a backfilled row is read history, not a run the
            # loop observed, and a single total would let one masquerade as the
            # other in the criterion that decides whether this layer earns its
            # keep.
            document["observations"] = store.observation_counts_by_source()
        finally:
            store.close()
    return document


def cmd_doctor(args: argparse.Namespace) -> int:
    as_json = bool(getattr(args, "json", False))
    try:
        paths = get_paths()
    except ConfigError as exc:
        if as_json:
            _emit({"ok": False, "error": str(exc), "status": "FAIL"})
            return 1
        print(f"Agent OS Doctor\n  [FAIL] {exc}")
        return 1

    if as_json:
        document = _doctor_document(paths)
        _emit(document)
        return 0 if document["ok"] else 1

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
    print(f"  schema:        {_schema_line(paths.db_path)}")
    print()
    print(f"Status: {'READY' if lifecycle else 'FOUNDATION ONLY'}")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    payload = _read_payload(args)
    declared = payload.get("schema_version", "")
    errors = validate_request(payload, phase="preflight")
    if errors:
        doc = _rejected(
            fallback_preflight(
                "invalid preflight request",
                task_id=str(payload.get("task_id") or ""),
                session_id=str(payload.get("session_id") or ""),
                schema_version=declared,
            ),
            errors,
        )
        validate_preflight(doc)
        _emit(doc)
        return BAD_REQUEST

    lifecycle = _load_lifecycle()
    if lifecycle is None:
        doc = fallback_preflight(
            "core lifecycle not yet ported",
            task_id=payload.get("task_id", ""),
            session_id=payload.get("session_id", ""),
            schema_version=declared,
        )
    else:
        doc = lifecycle.preflight(
            task=payload.get("task", ""),
            task_id=payload.get("task_id", ""),
            session_id=payload.get("session_id", ""),
            cwd=payload.get("cwd", ""),
            memory_mode=payload.get("memory_mode", "enabled"),
            provider=payload.get("provider", "host_delegate"),
            model=payload.get("model", ""),
            schema_version=declared,
        )
    validate_preflight(_note_unread(doc, payload, phase="preflight"))
    _emit(doc)
    return 0


def cmd_postflight(args: argparse.Namespace) -> int:
    payload = _read_payload(args)
    declared = payload.get("schema_version", "")
    errors = validate_request(payload, phase="postflight")
    if errors:
        doc = _rejected(
            fallback_postflight(
                "invalid postflight request",
                task_id=str(payload.get("task_id") or ""),
                loop_id=str(payload.get("loop_id") or ""),
                session_id=str(payload.get("session_id") or ""),
                schema_version=declared,
            ),
            errors,
        )
        validate_postflight(doc)
        _emit(doc)
        return BAD_REQUEST

    lifecycle = _load_lifecycle()
    if lifecycle is None:
        doc = fallback_postflight(
            "core lifecycle not yet ported",
            task_id=payload.get("task_id", ""),
            loop_id=payload.get("loop_id", ""),
            session_id=payload.get("session_id", ""),
            schema_version=declared,
        )
    else:
        # Every field the lifecycle can act on is forwarded. This list is the
        # learning signal's only path into the engine; dropping from it is what
        # made every host-delegated run record itself as a success.
        #
        # `collect_signals` accepts both a nested `signals` object and the flat
        # keys, so a plugin can send whichever it already has.
        signals = collect_signals(payload)
        doc = lifecycle.postflight(
            task_id=payload.get("task_id", ""),
            loop_id=payload.get("loop_id", ""),
            session_id=payload.get("session_id", ""),
            cwd=payload.get("cwd", ""),
            outcome=payload.get("outcome", ""),
            quality_score=payload.get("quality_score"),
            test_command=payload.get("test_command", ""),
            test_stdout=payload.get("test_stdout", ""),
            test_stderr=payload.get("test_stderr", ""),
            test_exit_code=payload.get("test_exit_code"),
            compile_command=payload.get("compile_command", ""),
            expected_files=payload.get("expected_files"),
            validate=bool(payload.get("validate", True)),
            signals=signals,
            schema_version=declared,
        )
    validate_postflight(_note_unread(doc, payload, phase="postflight"))
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
        compile_command=args.compile_command,
        expected_files=args.expect,
        validate=not args.no_validate,
    )
    validate_postflight(doc)
    _emit(doc)
    return 0


def _split_list(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _memory_list(args: argparse.Namespace, store) -> int:
    memories = store.list_memories(
        type=getattr(args, "type", None),
        status=getattr(args, "status", None),
        lane=getattr(args, "lane", None),
        scope=getattr(args, "scope", None),
    )
    limit = getattr(args, "limit", 0) or 0
    if limit:
        memories = memories[:limit]
    if not memories:
        print("(no memories)")
        return 0
    for m in memories:
        print(
            f"{m['memory_id']:<17} {m['type']:<11} {m['status']:<11} {m['lane']:<10} "
            f"{m['evidence_level']:<24} used={m['use_count']}/{m['success_count']:<3} "
            f"decay={m['decay_factor']:<5} {m['title']}"
        )
    print(f"\n{len(memories)} memories")
    return 0


def _memory_add(args: argparse.Namespace, store) -> int:
    from aos.core.memory import authoring

    try:
        row = authoring.new_memory(
            title=args.title,
            body=args.body,
            type=args.type,
            category=args.category,
            tags=_split_list(args.tags),
            roles=_split_list(args.roles),
            evidence_level=args.evidence_level,
            confidence=args.confidence,
            status=args.status,
            scope=args.scope,
            when_to_apply=args.when,
            revalidate_after=args.revalidate_after,
            source_project=args.source_project,
            verified=args.verified,
        )
    except authoring.AuthoringError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    from aos.core.learning import dedupe as dedupe_mod

    try:
        store.upsert_memory(row, tags=row["tags"], roles=row["roles"])
    except sqlite3.IntegrityError:
        # The unique (scope, dedupe_key) index caught a restatement of a fact the
        # store already holds. A traceback tells the author nothing they can act
        # on; the existing row's id does.
        existing = store.find_by_dedupe_key(row["scope"], dedupe_mod.key_for(row))
        if existing:
            print(
                f"同一事实已存在：{existing['memory_id']} 「{existing['title']}」"
                f"（scope={row['scope']}，status={existing['status']}）",
                file=sys.stderr,
            )
            print(
                "它确实是另一件事 → 改措辞；只是在支持这条既有记忆 → "
                f"aos memory inspect {existing['memory_id']}，让运行的证据替它说话",
                file=sys.stderr,
            )
        else:
            print("该 scope 下已有相同事实的记录，未写入。", file=sys.stderr)
        return 2

    _emit(row)
    return 0


def _memory_refresh(args: argparse.Namespace, store) -> int:
    from aos.core.memory import evolve

    report = evolve.refresh_store(store=store, today=getattr(args, "today", "") or "")
    if getattr(args, "json", False):
        _emit(report)
        return 0
    print(f"过期降级: {len(report['expired'])} 条")
    for move in report["expired"]:
        print(f"  {move['memory_id']}: {move['from']} -> {move['to']}（到期 {move['revalidate_after']}）")
    print(f"补齐 dedupe_key: {len(report['dedupe_keys_filled'])} 条")
    print(f"重算判定计数: {report['observation_counts_refreshed']} 条")
    summary = report["decay"]
    print(f"衰减: active {summary['active']} / degraded {summary['degraded']} / archived_candidate {summary['archived_candidate']}")
    return 0


def _memory_seed(args: argparse.Namespace, store) -> int:
    from aos.config import get_paths
    from aos.core.memory import authoring

    directory = Path(args.dir) if args.dir else get_paths().memory_dir
    report = authoring.seed_from_dir(directory, store=store, force=args.force)
    _emit(report)
    return 1 if report["errors"] and not report["seeded"] else 0


def _memory_migrate(args: argparse.Namespace, store) -> int:
    from aos.core.memory import migrations

    try:
        report = migrations.migrate(
            store.conn,
            to=args.to if args.to is not None else migrations.LATEST_VERSION,
            dry_run=args.dry_run,
            db_path=store.db_path,
        )
    except migrations.SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        report["would_apply"] = report.pop("planned")
    _emit(report)
    return 0


def _memory_show(args: argparse.Namespace, store) -> int:
    for row in store.memories_for_scoring():
        if row["memory_id"] == args.memory_id:
            _emit(row)
            return 0
    print(f"error: no memory {args.memory_id}", file=sys.stderr)
    return 1


def _memory_inspect(args: argparse.Namespace, store) -> int:
    """Everything the store can say about one memory, and why it believes it.

    The point is the trace: a memory that cannot be followed back to the loop,
    task, session and evidence that produced it is a claim with no way to check
    it, which is the failure mode this store exists to avoid.
    """
    memory = next(
        (row for row in store.memories_for_scoring() if row["memory_id"] == args.memory_id), None
    )
    if memory is None:
        print(f"error: no memory {args.memory_id}", file=sys.stderr)
        return 1

    observations = store.list_observations(memory_id=args.memory_id)
    candidates = [c for c in store.list_candidates() if c.get("target_memory") == args.memory_id]
    reviews = [r for r in store.list_reviews() if r.get("memory_id") == args.memory_id]
    lineage = {
        "supersedes": memory.get("supersedes", ""),
        "superseded_by": sorted(
            row["memory_id"]
            for row in store.memories_for_scoring()
            if row.get("supersedes") == args.memory_id
        ),
        "version": memory.get("version", 1),
    }
    _emit(
        {
            "memory": memory,
            "lifecycle": {
                "status": memory.get("status"),
                "lane": memory.get("lane"),
                "scope": memory.get("scope"),
                "evidence_level": memory.get("evidence_level"),
                "confidence": memory.get("confidence"),
                "created_at": memory.get("created_at"),
                "last_verified_at": memory.get("last_verified_at"),
                "revalidate_after": memory.get("revalidate_after"),
                "decay_factor": memory.get("decay_factor"),
                "observation_count": memory.get("observation_count"),
                "use_count": memory.get("use_count"),
                "success_count": memory.get("success_count"),
                "last_used_at": memory.get("last_used_at"),
            },
            "provenance": {
                "source_project": memory.get("source_project"),
                "source_task": memory.get("source_task"),
                "source_loop_id": memory.get("source_loop_id"),
                "source_session": memory.get("source_session"),
                "source_evidence": memory.get("source_evidence"),
                "loops": sorted({obs.get("loop_id", "") for obs in observations if obs.get("loop_id")}),
                "sessions": sorted(
                    {obs.get("session_id", "") for obs in observations if obs.get("session_id")}
                ),
            },
            "lineage": lineage,
            "observations": observations,
            "candidates": candidates,
            "reviews": reviews,
        }
    )
    return 0


_MEMORY_COMMANDS = {
    "list": _memory_list,
    "add": _memory_add,
    "refresh": _memory_refresh,
    "seed": _memory_seed,
    "show": _memory_show,
    "inspect": _memory_inspect,
    "migrate": _memory_migrate,
}


def cmd_backfill(args: argparse.Namespace) -> int:
    """The only way history enters the store, and it is closed by default.

    Nothing is read unless `AOS_BACKFILL_DB` names a database. That is not
    shyness: the source holds other people's conversations, so the whitelist in
    `aos/backfill.py` decides what may be looked at, and this command refuses to
    guess where the file is.
    """
    from aos import backfill

    command = getattr(args, "backfill_command", None) or "plan"
    try:
        if command == "plan":
            document = backfill.plan()
        else:
            document = backfill.run(
                apply=bool(getattr(args, "apply", False)),
                limit=int(getattr(args, "limit", 0) or 0),
                reset=bool(getattr(args, "reset", False)),
            )
    except backfill.BackfillError as exc:
        _emit({"ok": False, "reason": str(exc)})
        return 1

    _emit(document)
    if not document.get("ok", True):
        return 1
    if command == "run" and document.get("applied") is False:
        print("(dry run: pass --apply to write)", file=sys.stderr)
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    """Read-only view of the open loops. A host gets here with a sessionID alone,
    which is all opencode's idle event carries.
    """
    from aos.core.loop import pending

    if args.session:
        entry = pending.find(args.session)
        payload = {"session_id": args.session, "found": entry is not None, "loop": entry}
    else:
        payload = pending.summary() | {"loops": pending.list_pending()}

    _emit(payload)
    return 0 if (args.session == "" or payload["found"]) else 1


def cmd_memory(args: argparse.Namespace) -> int:
    from aos.core.memory.store import MemoryStore

    handler = _MEMORY_COMMANDS.get(getattr(args, "memory_command", None) or "list")
    if handler is None:
        print("usage: aos memory list|add|seed|refresh|migrate|show|inspect", file=sys.stderr)
        return 1

    store = MemoryStore()
    try:
        return handler(args, store)
    finally:
        store.close()


def _describe_review(review: dict[str, Any]) -> str:
    """One review, rendered for the person who has to decide it.

    An outcome-label review shows the *evidence* rather than a verdict, because
    the verdict is what is being asked for; a promotion review shows what approving
    would change, because approving must not surprise anyone.
    """
    evidence = review.get("evidence") or {}
    change = review.get("proposed_change") or {}
    kind = review.get("kind", "promotion")

    if kind == "outcome_label":
        signals = evidence.get("signals") or {}
        shown = ", ".join(
            f"{key}={signals[key]}" for key in sorted(signals) if signals[key] not in (None, "", [], {})
        ) or "nothing"
        memories = evidence.get("memories_used") or []
        decided = review.get("status") != "pending"
        action = (
            f"      已标注: {review.get('outcome') or '-'}（{review['status']}）"
            if decided
            else f"      -> aos review label {review['review_id']} --outcome success|partial|failure"
        )
        return (
            f"#{review['review_id']:<4} label    loop={review.get('loop_id') or '-':<14} "
            f"engine said={evidence.get('outcome')} confidence={evidence.get('confidence')} "
            f"mass={evidence.get('mass')}\n"
            f"      任务: {evidence.get('task') or '(unknown)'}\n"
            f"      信号: {shown}\n"
            f"      缺席: {', '.join(evidence.get('absent') or []) or '-'}\n"
            f"      涉及记忆: {', '.join(memories) or '(none recalled)'}\n" + action
        )

    if kind == "conflict":
        existing = evidence.get("existing") or {}
        proposed = evidence.get("proposed") or {}
        new_row = (change.get("new") or {})
        return "\n".join(
            [
                f"#{review['review_id']:<4} {review['status']:<8} conflict {review['memory_id']:<12} "
                f"相似={evidence.get('ratio')} tag重叠={evidence.get('tag_jaccard')}",
                f"      已有: {existing.get('title') or '(gone)'}  [{existing.get('status') or '-'}]",
                f"      提案: {proposed.get('title') or '(none)'}",
                f"      内容: {(proposed.get('body') or '')[:160]}",
                f"      批准后: {review['memory_id']} -> superseded，"
                f"{new_row.get('memory_id') or '(新条目)'} 取代它（active，证据仍为 hypothesis）",
                f"      拒绝则: 保留 {review['memory_id']}，提案作废",
                f"      -> aos review approve {review['review_id']} | reject {review['review_id']}",
            ]
        )

    changes = change.get("changes") or {}
    before = change.get("before") or {}
    moved = ", ".join(
        f"{key}: {before.get(key, '-')!r} -> {value!r}" for key, value in changes.items()
    ) or "nothing"
    proposal = evidence.get("proposal") or {}
    runs_now = review.get("runs_now")
    opened_runs = evidence.get("validation_runs", 0)
    runs_label = f"runs={runs_now}" if runs_now is not None else f"runs={opened_runs}"
    if runs_now is not None and runs_now > opened_runs:
        runs_label += f"（提案提出后又收集到 {runs_now - opened_runs} 次）"
    lines = [
        f"#{review['review_id']:<4} {review['status']:<8} {kind} {review['memory_id']:<16} "
        f"{runs_label} quality={evidence.get('quality_score', 0)}"
    ]
    if change.get("kind") == "create":
        lines.append(f"      新建: [{proposal.get('type')}] {proposal.get('title', '')}")
        lines.append(f"      内容: {proposal.get('body', '')}")
    lines.append(f"      批准后: {moved}")
    lines.append(f"      原因: {evidence.get('reason') or change.get('reason') or ''}")
    return "\n".join(lines)


def cmd_review(args: argparse.Namespace) -> int:
    from aos.core.memory import evolve

    command = getattr(args, "review_command", None) or "list"

    if command == "list":
        reviews = evolve.list_reviews(status=getattr(args, "status", None))
        if getattr(args, "json", False):
            _emit(reviews)
            return 0
        if not reviews:
            print("(no reviews)")
            return 0
        for review in reviews:
            print(_describe_review(review))
            print()
        pending = [r for r in reviews if r["status"] == "pending"]
        labels = [r for r in pending if r.get("kind") == "outcome_label"]
        print(f"{len(reviews)} reviews ({len(pending)} pending, {len(labels)} waiting for a label)")
        return 0

    if command == "sync":
        _emit(evolve.run_learning())
        return 0

    if command == "label":
        results = [
            evolve.label_review(
                review_id, args.outcome, quality_score=args.quality, skill_used=args.skill or ""
            )
            for review_id in args.review_ids
        ]
        for result in results:
            if result["status"] == "approved":
                _report_attribution(result["review_id"], args.outcome, result)
        if len(results) == 1:
            _emit(results[0])
        else:
            _emit({"labelled": [r["review_id"] for r in results if r["status"] == "approved"],
                   "skipped": [{"review_id": r["review_id"], "status": r["status"]}
                               for r in results if r["status"] != "approved"]})
        return 0 if all(r["status"] == "approved" for r in results) else 1

    if command in ("approve", "reject"):
        if command == "approve":
            result = evolve.approve_review(args.review_id)
            expected = "approved"
        else:
            result = evolve.reject_review(
                args.review_id,
                as_outcome=getattr(args, "as_outcome", "") or "",
                skill_used=getattr(args, "skill", "") or "",
            )
            expected = "rejected"
        if result.get("relabelled"):
            _report_attribution(
                args.review_id, getattr(args, "as_outcome", "") or "", result["relabelled"]
            )
        _emit(result)
        return 0 if result["status"] == expected else 1

    print(
        "usage: aos review list [--status STATUS] [--json] | sync"
        " | label <id...> --outcome X [--skill S] | approve <id> | reject <id> [--as X [--skill S]]",
        file=sys.stderr,
    )
    return 1


def _report_attribution(review_id: int, outcome: str, verdict: dict) -> None:
    """A verdict that blamed nothing is worth saying out loud.

    The queue's own hint pushes `--outcome`; without `--skill` the run is judged and
    every memory in it is left alone. That is the intended default, but a person who
    does not know it will conclude the loop did nothing.
    """
    if verdict.get("candidates_created") or verdict.get("blamed_memories"):
        return
    print(
        f"#{review_id}: 结论已记为 {outcome}，但未点名 skill ⇒ 没有归因任何记忆"
        f"（召回过 ≠ 造成了结果）。这条评审已经定了，归因补不回来；"
        f"下次标注时直接写：aos review label <id> --outcome {outcome} --skill <这次的工种，如 bugfix>",
        file=sys.stderr,
    )


# ── Parser ─────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    # Imported here rather than at module scope so the contract-only commands
    # stay free of the storage layer, as they were before.
    from aos.contract.schema import MEMORY_LANE, MEMORY_TYPE
    from aos.core.memory.authoring import CONFIDENCE_LEVELS, STATUSES
    from aos.core.outcome import OUTCOMES
    from aos.core.memory.evolve import EVIDENCE_LEVELS

    parser = argparse.ArgumentParser(
        prog="aos",
        description="Agent OS — routing, memory and evolution for coding agents",
    )
    parser.add_argument("--version", action="store_true", help="show version and exit")
    sub = parser.add_subparsers(dest="command")

    p_doctor = sub.add_parser("doctor", help="diagnose the Agent OS environment")
    p_doctor.add_argument("--json", action="store_true", help="emit the machine-readable report")

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
    p_run.add_argument("--provider", default="host_delegate")
    p_run.add_argument("--model", default="")
    p_run.add_argument("--test-command", default="", help="test command to record as evidence")
    p_run.add_argument("--test-exit-code", type=int, default=None, help="test exit code (0 = pass)")
    p_run.add_argument("--compile-command", default="", help="compile/build command for validation")
    p_run.add_argument("--expect", action="append", default=None, help="expected changed file (repeatable)")
    p_run.add_argument("--no-validate", action="store_true", help="skip post-execution code validation")

    p_pending = sub.add_parser(
        "pending",
        help="loops that opened and have not reported back (the plugin's lookup surface)",
    )
    p_pending.add_argument("--session", default="", help="look up one session instead of the summary")
    p_pending.add_argument("--json", action="store_true", help="emit JSON")

    p_backfill = sub.add_parser(
        "backfill",
        help="read past runs out of another tool's database — off unless AOS_BACKFILL_DB is set",
    )
    backfill_sub = p_backfill.add_subparsers(dest="backfill_command")
    backfill_sub.add_parser("plan", help="what would be read, writing nothing")
    p_bf_run = backfill_sub.add_parser("run", help="read it, once, from the watermark")
    p_bf_run.add_argument("--apply", action="store_true", help="write observations (default is a dry run)")
    p_bf_run.add_argument("--limit", type=int, default=0, help="at most N sessions this pass")
    p_bf_run.add_argument(
        "--reset",
        action="store_true",
        help="drop our own backfill rows first — only ever after the source opened successfully",
    )

    p_memory = sub.add_parser("memory", help="author and inspect the memory store")
    mem_sub = p_memory.add_subparsers(dest="memory_command")

    p_mem_list = mem_sub.add_parser("list", help="list memories")
    p_mem_list.add_argument("--type", default=None, choices=sorted(MEMORY_TYPE))
    p_mem_list.add_argument("--status", default=None, choices=list(STATUSES))
    p_mem_list.add_argument("--lane", default=None, choices=sorted(MEMORY_LANE))
    p_mem_list.add_argument("--scope", default=None, help="global | project:<id> | session:<id>")
    p_mem_list.add_argument("--limit", type=int, default=0, help="show at most N rows")

    p_mem_add = mem_sub.add_parser("add", help="author one memory by hand")
    p_mem_add.add_argument("--title", required=True, help="one line, shown when the budget is tight")
    p_mem_add.add_argument("--body", required=True, help="the lesson itself")
    p_mem_add.add_argument("--type", default="episodic", choices=sorted(MEMORY_TYPE))
    p_mem_add.add_argument(
        "--category",
        default="",
        help="a router skill id (bugfix, security, test, ...) — other values never match",
    )
    p_mem_add.add_argument("--tags", default="", help="comma separated; the strongest scoring term")
    p_mem_add.add_argument("--roles", default="", help="comma separated role ids")
    p_mem_add.add_argument("--evidence-level", default="hypothesis", choices=list(EVIDENCE_LEVELS))
    p_mem_add.add_argument("--confidence", default="low", choices=list(CONFIDENCE_LEVELS))
    p_mem_add.add_argument(
        "--status",
        default=None,
        choices=list(STATUSES),
        help="only the gate may set verified; an unverified memory is born candidate",
    )
    p_mem_add.add_argument("--scope", default="global", help="global | project:<id> | session:<id>")
    p_mem_add.add_argument(
        "--when",
        default="",
        help="the trigger clause: when this applies. Without it the memory reads as an unmotivated fact",
    )
    p_mem_add.add_argument(
        "--revalidate-after",
        default="",
        help="YYYY-MM-DD after which the memory must be re-checked (facts about a version need one)",
    )
    p_mem_add.add_argument("--source-project", default="", help="where the fact was learned")
    p_mem_add.add_argument(
        "--verified",
        action="store_true",
        help="keep the claimed evidence_level; without it a memory is demoted to hypothesis",
    )

    p_mem_refresh = mem_sub.add_parser(
        "refresh",
        help="recompute derived state: expiry, fact keys, judged-run counts, decay",
    )
    p_mem_refresh.add_argument("--today", default="", help="override the date used for expiry (YYYY-MM-DD)")
    p_mem_refresh.add_argument("--json", action="store_true", help="emit the report as JSON")
    p_mem_seed = mem_sub.add_parser("seed", help="load content/memory/**/*.json into the store")
    p_mem_seed.add_argument("--dir", default=None, help="seed directory (default: the content memory dir)")
    p_mem_seed.add_argument("--force", action="store_true", help="rewrite entries that already exist")

    p_mem_migrate = mem_sub.add_parser(
        "migrate", help="bring the database up to the engine's schema version"
    )
    p_mem_migrate.add_argument("--to", type=int, default=None, help="stop at this schema version")
    p_mem_migrate.add_argument(
        "--dry-run", action="store_true", help="report what would run without touching the file"
    )

    for name, help_text in (
        ("show", "print one memory as JSON"),
        ("inspect", "one memory plus its observations, candidates and reviews"),
    ):
        p_mem_detail = mem_sub.add_parser(name, help=help_text)
        p_mem_detail.add_argument("memory_id", help="memory id")

    p_review = sub.add_parser("review", help="the human gate: label runs, decide reviews")
    review_sub = p_review.add_subparsers(dest="review_command")
    review_sub.add_parser(
        "sync",
        help="run one learning cycle now (settle unconsumed candidates into the queue)",
    )
    p_review_list = review_sub.add_parser("list", help="list learning reviews")
    p_review_list.add_argument(
        "--status",
        choices=["pending", "approved", "rejected", "stale"],
        default=None,
        help="filter by status",
    )
    p_review_list.add_argument("--json", action="store_true", help="emit the reviews as JSON")
    for action in ("approve", "reject"):
        p_action = review_sub.add_parser(action, help=f"{action} a pending review")
        p_action.add_argument("review_id", type=int, help="review id")
        if action == "reject":
            p_action.add_argument(
                "--as",
                dest="as_outcome",
                choices=list(OUTCOMES),
                default="",
                help="also relabel the run this review came from, so a rejection "
                     "becomes a weakening signal instead of a shrug",
            )
            p_action.add_argument(
                "--skill",
                default="",
                help="with --as: which kind of work this verdict is evidence about "
                     "(e.g. bugfix, migration). Without it no memory is blamed",
            )
    p_label = review_sub.add_parser("label", help="answer an outcome-label review")
    p_label.add_argument(
        "review_ids",
        type=int,
        nargs="+",
        help="one or more label reviews — a queue of the same verdict is answered in one go",
    )
    p_label.add_argument("--outcome", required=True, choices=list(OUTCOMES), help="what the run achieved")
    p_label.add_argument(
        "--skill",
        default="",
        help="which kind of work this verdict is evidence about (e.g. bugfix). Without it "
             "no memory is credited or blamed: being recalled is not being the cause",
    )
    p_label.add_argument(
        "--quality",
        type=float,
        default=None,
        help="quality score to record instead of the default for that outcome",
    )

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
        "backfill": cmd_backfill,
        "memory": cmd_memory,
        "pending": cmd_pending,
        "review": cmd_review,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
