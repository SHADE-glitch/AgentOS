"""Decide what a finished loop actually achieved.

OpenCode has no hook that returns a verdict: ``session.idle`` looks identical
whether the task succeeded or the user gave up, so if the engine wants a learning
signal at all it has to synthesise one. This module is that synthesis — pure,
deterministic, stdlib, and deliberately ignorant of anything it was not told.

The output is not just an outcome but its own **confidence**, defined as signal
*coverage* rather than agreement: ``mass`` is the total weight of the signals that
were actually present. A run with a passing test suite scores high confidence; a
delegated run that reported nothing scores 0.0 and is handed to a human as
``needs_review``, because the honest answer to "did that work?" is "I was not told,
and I will not guess". Silently recording ``success`` in that case is how every
loop in this engine once got logged as a win, which made the main learning signal a
constant and the loop stop learning while its tables kept growing.
"""

from __future__ import annotations

from typing import Any, Optional

from aos.core.memory.policy import load_policy

OUTCOMES = ("success", "partial", "failure")

# Each signal contributes a value in [0, 1] and a weight. A signal the host did
# not report is *absent*, not zero: scoring an absent signal as 0.0 would punish a
# run for the host's lack of instrumentation, and would make mass meaningless.
_SIGNALS = (
    "test_exit_code",
    "build_exit_code",
    "validation_status",
    "user_interrupted",
    "session_error",
    "tool_errors",
    "todos_unfinished",
    "expected_files",
    "diff",
    "response_summary",
    # Echoed, never scored. This tuple — not `SIGNAL_FIELDS` — decides what survives synthesis
    # into the row a human will read, so a trajectory declared only in the contract is discarded
    # here before the store ever sees it.
    "tool_trace",
    "tool_calls",
)

_VALIDATION_VALUES = {"PASS": 1.0, "PARTIAL": 0.5, "FAIL": 0.0, "BLOCKED": 0.0}


def _is_present(received: dict[str, Any], name: str) -> bool:
    """Whether the host actually said something about this signal.

    ``0`` is present and means "instrumented, nothing wrong"; a missing key (or an
    explicit null) means the host does not report it. Collapsing the two would
    score an uninstrumented host as a host with perfect numbers, and would inflate
    ``mass`` — which is supposed to measure how much we were told.
    """
    if name not in received:
        return False
    value = received[name]
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _test_value(value: Any) -> float:
    """Exit code 0 is the one unambiguous signal a host can send."""
    try:
        return 1.0 if int(value) == 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _validation_value(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        # The engine's validator calls it `validation_status`; a host may send the
        # shorter `status`. Both mean the same enumerated verdict.
        value = value.get("validation_status") or value.get("status")
    if value is None:
        return None
    return _VALIDATION_VALUES.get(str(value).upper())


def _error_count_value(value: Any, limit: int) -> float:
    """Fewer errors is better, capped, so a wall of failures is not 50x a couple."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 - min(max(count, 0), limit) / float(limit)


def _expected_files_value(expected: Any, changed: list[str]) -> Optional[float]:
    if not expected:
        return None
    wanted = [str(item) for item in expected]
    hit = sum(1 for item in wanted if any(item in str(path) for path in changed))
    return hit / float(len(wanted))


def _diff_value(diff: Any) -> float:
    """An empty diff is suspicious but legitimate for analysis tasks, so it only
    carries the smallest weight in the table."""
    if isinstance(diff, dict):
        return 1.0 if (diff.get("files") or diff.get("additions") or diff.get("deletions")) else 0.0
    if isinstance(diff, (list, tuple)):
        return 1.0 if len(diff) else 0.0
    return 1.0 if diff else 0.0


def _file_of(entry: Any) -> str:
    """opencode reports diffs as objects (``FileDiff{file, before, after, …}``).

    Stringifying such an entry whole would give `expected_files` a hash-shaped
    string to look for, so no file would ever match and every run would score 0.
    """
    if isinstance(entry, dict):
        for key in ("file", "path", "filename"):
            value = entry.get(key)
            if value:
                return str(value)
        return ""
    return str(entry).strip()


def _changed_files(engine_evidence: dict[str, Any], signals: dict[str, Any]) -> list[str]:
    evidence = engine_evidence or {}
    for source in (
        evidence.get("files_changed"),
        signals.get("files_changed"),
        evidence.get("diff"),
        signals.get("diff"),
    ):
        if isinstance(source, dict):
            source = source.get("files")
        if isinstance(source, (list, tuple)):
            paths = [path for path in (_file_of(item) for item in source) if path]
            if paths:
                return paths
        elif isinstance(source, str) and source.strip():
            return [source.strip()]
    return []


def synthesize(
    signals: Optional[dict[str, Any]] = None,
    *,
    engine_evidence: Optional[dict[str, Any]] = None,
    policy: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Turn whatever was reported into an outcome plus the confidence in it.

    Returns ``{"outcome", "quality_score", "confidence", "mass", "score",
    "needs_review", "synthesised", "explicit", "signals", "present", "absent",
    "reasons"}``. ``signals`` is the received set, normalised and echoed back, so
    the row in the store can be reviewed later without re-deriving anything.
    """
    rules = {**load_policy("outcome"), **(policy or {})}
    weights = {**rules["weights"], **(rules.get("weight_overrides") or {})}
    received = dict(signals or {})
    evidence = dict(engine_evidence or {})

    report: dict[str, Any] = {
        "outcome": "partial",
        "quality_score": 0.0,
        "confidence": 0.0,
        "mass": 0.0,
        "score": None,
        "needs_review": True,
        "synthesised": False,
        "explicit": False,
        "signals": {},
        "present": [],
        "absent": [],
        "reasons": [],
    }

    # 1. A host that judged its own work is not overruled by arithmetic. It is
    # also the only case where confidence is 1.0 rather than measured.
    declared = str(received.get("outcome") or "").strip().lower()
    if declared in OUTCOMES:
        quality = received.get("quality_score")
        return {
            **report,
            "outcome": declared,
            "quality_score": round(float(quality), 2)
            if isinstance(quality, (int, float))
            else float(rules[f"{declared}_quality"]),
            "confidence": 1.0,
            "mass": 1.0,
            "score": None,
            "needs_review": False,
            "explicit": True,
            "signals": {"outcome": declared},
            "present": ["outcome"],
            "absent": [name for name in _SIGNALS if name not in received],
            "reasons": [f"host reported {declared}"],
        }

    # 2. Anything that means "this did not finish" dominates a weighted average.
    # A signal whose weight has been overridden to zero is a signal the operator
    # decided not to trust, so it loses the power to veto too — that veto is what
    # makes it decisive, not its presence.
    hard_fail: list[str] = [
        reason
        for reason, present_value in (
            ("user_interrupted", received.get("user_interrupted")),
            ("session_error", received.get("session_error")),
        )
        if present_value and float(weights.get(reason, 0.0)) > 0.0
    ]
    for name in ("test_exit_code", "build_exit_code"):
        value = received.get(name)
        if (
            value is not None
            and float(weights.get(name, 0.0)) > 0.0
            and _test_value(value) == 0.0
        ):
            hard_fail.append(f"{name}={value}")

    changed = _changed_files(evidence, received)
    contributions: dict[str, float] = {}
    present: list[str] = []
    absent: list[str] = []

    def consider(name: str, value: Optional[float], is_present: bool) -> None:
        if not is_present or value is None:
            absent.append(name)
            return
        present.append(name)
        contributions[name] = float(value)

    cap = int(rules["error_cap"])
    validation = _validation_value(evidence.get("validation") or evidence.get("validation_status"))
    diff_reported = _is_present(received, "diff")

    consider("test_exit_code", _test_value(received.get("test_exit_code")), _is_present(received, "test_exit_code"))
    consider("build_exit_code", _test_value(received.get("build_exit_code")), _is_present(received, "build_exit_code"))
    consider("validation_status", validation, validation is not None)
    consider("user_interrupted", 0.0 if received.get("user_interrupted") else 1.0, _is_present(received, "user_interrupted"))
    consider("session_error", 0.0 if received.get("session_error") else 1.0, _is_present(received, "session_error"))
    consider("tool_errors", _error_count_value(received.get("tool_errors"), cap), _is_present(received, "tool_errors"))
    consider("todos_unfinished", _error_count_value(received.get("todos_unfinished"), cap), _is_present(received, "todos_unfinished"))
    expected_value = _expected_files_value(received.get("expected_files"), changed)
    consider("expected_files", expected_value, expected_value is not None)
    # The engine's own set-difference of changed files is evidence of a diff even
    # when the host sent no `diff` key; "nothing changed anywhere" is absence,
    # because it is indistinguishable from not having looked.
    consider("diff", _diff_value(received.get("diff") if diff_reported else changed), diff_reported or bool(changed))
    # Computed and reported, never counted: pattern-matching a model's own prose
    # for words like "done" is not evidence. It stays at weight 0.00 so a host can
    # see it was read without the score quietly depending on it.
    consider(
        "response_summary",
        1.0 if _is_present(received, "response_summary") else 0.0,
        _is_present(received, "response_summary"),
    )
    # The trajectory is reported the same way: listed so a reviewer can see it was sent, weighted 0.00
    # so it cannot add coverage. An empty list counts as *not said* — a host that reports zero
    # attempts has not described the run's process, it has described nothing.
    trace_present = _is_present(received, "tool_trace") and bool(received.get("tool_trace"))
    consider("tool_trace", 1.0 if trace_present else 0.0, trace_present)
    consider("tool_calls", 1.0, _is_present(received, "tool_calls"))

    mass = sum(float(weights.get(name, 0.0)) for name in present)
    score = (
        sum(float(weights.get(name, 0.0)) * contributions[name] for name in present) / mass
        if mass > 0
        else None
    )
    confidence = min(1.0, mass)

    # A weighted average of 5% coverage is not a verdict. `min_verdict_mass` is the
    # floor below which the arithmetic is not allowed to call anything a failure or
    # a success, so the run goes to the human gate instead — the alternative is a
    # single 0.05-weight empty diff condemning an entire loop.
    verdict_mass = float(rules["min_verdict_mass"])
    thresholds = rules["thresholds"]
    trusted = score is not None and mass >= verdict_mass
    if hard_fail:
        outcome = "failure"
    elif not trusted:
        outcome = str(rules["no_signal_outcome"])
    elif score >= float(thresholds["success"]):
        outcome = "success"
    elif score >= float(thresholds["partial"]):
        outcome = "partial"
    else:
        outcome = "failure"

    # Quality has to agree with the verdict, not with the arithmetic: the learning
    # gate reads `quality_score >= promotion.threshold` to decide whether to
    # reinforce a memory, so a hard failure — or a run whose score was too thin to
    # be trusted — carrying the number of a successful run would reward the
    # memories that were in play when it fell over.
    if hard_fail or not trusted:
        quality = float(rules[f"{outcome}_quality"])
    else:
        quality = round(5.0 * score, 2)

    reasons = list(hard_fail)
    if score is None:
        reasons.append("no weighted signal was reported")
    elif not trusted and not hard_fail:
        reasons.append(
            f"signals cover mass={round(mass, 3)}, below min_verdict_mass={verdict_mass}; not called either way"
        )
    else:
        reasons.append(f"weighted score={round(score, 3)} over mass={round(mass, 3)}")
    for name in present:
        reasons.append(f"{name}={contributions[name]} weight={weights.get(name, 0.0)}")

    return {
        **report,
        "outcome": outcome,
        "quality_score": quality,
        "confidence": round(confidence, 3),
        "mass": round(mass, 3),
        "score": round(score, 3) if score is not None else None,
        "needs_review": confidence < float(rules["min_auto_confidence"]),
        "synthesised": True,
        "signals": {
            **{name: received[name] for name in _SIGNALS if name in received},
            "files_changed": changed,
        },
        "present": present,
        "absent": absent,
        "reasons": reasons,
    }
