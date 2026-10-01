"""Outcome synthesis tests.

The formula is table-driven on purpose: every case below is a signal set a host
can actually send, and the expected row is what the learning gate will then act
on. A synthesizer that is only tested by spot checks is a source of silent
mislearning, because its output decides which memories get reinforced.
"""

from __future__ import annotations

import pytest

from aos.core.memory.policy import load_policy
from aos.core.outcome import OUTCOMES, synthesize

DEFAULTS = {
    "weights": {
        "test_exit_code": 0.45,
        "build_exit_code": 0.20,
        "validation_status": 0.20,
        "user_interrupted": 0.20,
        "session_error": 0.20,
        "tool_errors": 0.10,
        "todos_unfinished": 0.10,
        "expected_files": 0.10,
        "diff": 0.05,
        "response_summary": 0.00,
        "tool_trace": 0.00,
        "tool_calls": 0.00,
    },
    "weight_overrides": {},
    "thresholds": {"success": 0.75, "partial": 0.40},
    "error_cap": 5,
    "min_auto_confidence": 0.60,
    "min_verdict_mass": 0.45,
    "no_signal_outcome": "partial",
    "success_quality": 3.5,
    "partial_quality": 0.0,
    "failure_quality": 0.0,
}


def _synth(signals, evidence=None, **overrides):
    return synthesize(signals, engine_evidence=evidence or {}, policy={**DEFAULTS, **overrides})


# ── the host's own verdict wins ────────────────────────────────────────
@pytest.mark.parametrize("declared", OUTCOMES)
def test_an_explicit_host_verdict_is_believed_without_arithmetic(declared):
    """A host that judged its own work is not overruled by a weighted average.

    The engine cannot see whether opencode did the right thing; the host can.
    """
    result = _synth({"outcome": declared})
    assert result["outcome"] == declared
    assert result["confidence"] == 1.0
    assert result["explicit"] is True
    assert result["synthesised"] is False
    assert result["needs_review"] is False


def test_an_explicit_verdict_is_not_overruled_by_a_failing_test_it_reports():
    """Both fields came from the host; the verdict is the host's conclusion."""
    result = _synth({"outcome": "partial", "test_exit_code": 1})
    assert result["outcome"] == "partial"
    assert result["needs_review"] is False


def test_a_declared_quality_score_is_carried_through():
    result = _synth({"outcome": "success", "quality_score": 4.25})
    assert result["quality_score"] == pytest.approx(4.25)


def test_an_unknown_declared_outcome_falls_through_to_synthesis():
    result = _synth({"outcome": "maybe"})
    assert result["explicit"] is False
    assert result["synthesised"] is True


# ── the table ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "signals, evidence, expected",
    [
        # outcome, quality, confidence, needs_review — for each signal set.
        ({"test_exit_code": 0}, {}, {"outcome": "success", "confidence": 0.45, "needs_review": True}),
        ({"test_exit_code": 0, "diff": [{"file": "a.py"}]}, {}, {"outcome": "success", "confidence": 0.50}),
        ({"test_exit_code": 1}, {}, {"outcome": "failure", "quality_score": 0.0, "confidence": 0.45}),
        ({"build_exit_code": 2}, {}, {"outcome": "failure", "confidence": 0.20}),
        ({"user_interrupted": True, "test_exit_code": 0}, {}, {"outcome": "failure", "quality_score": 0.0}),
        ({"session_error": "boom", "test_exit_code": 0}, {}, {"outcome": "failure", "quality_score": 0.0}),
        ({}, {}, {"outcome": "partial", "score": None, "confidence": 0.0, "needs_review": True}),
        ({"diff": []}, {}, {"outcome": "partial", "confidence": 0.05, "needs_review": True}),
        # 3 tool errors is bad, but 0.25 coverage is not enough coverage to call a
        # run failed: it is enough to ask a human.
        ({"tool_errors": 3, "todos_unfinished": 0, "diff": [{"file": "x"}]},
         {}, {"outcome": "partial", "confidence": 0.25, "quality_score": 0.0, "needs_review": True}),
    ],
)
def test_signal_sets_map_to_the_expected_verdict(signals, evidence, expected):
    result = _synth(signals, evidence)
    for key, value in expected.items():
        actual = result[key]
        assert actual == (pytest.approx(value) if isinstance(value, float) else value), (
            f"{key}: signals={signals} expected {value!r}, got {actual!r}"
        )


def test_tests_passing_plus_engine_validation_is_confident_enough_to_be_automatic():
    """0.45 (test) + 0.20 (validation) = 0.65 ≥ 0.60: the intended automatic path.

    A host that runs the suite gets a trustworthy signal; one that only chats
    does not. That asymmetry is the design, not an oversight.
    """
    result = _synth({"test_exit_code": 0}, {"validation": {"status": "PASS"}})
    assert result["outcome"] == "success"
    assert result["confidence"] == pytest.approx(0.65)
    assert result["needs_review"] is False


def test_a_failing_build_overrides_a_clean_test_run():
    result = _synth({"test_exit_code": 0, "build_exit_code": 1})
    assert result["outcome"] == "failure"


def test_tool_errors_saturate_rather_than_scaling_forever():
    """5 and 500 errors are the same evidence of a bad run; the cap keeps the
    weighted average from being dominated by one noisy counter."""
    few = _synth({"tool_errors": 5, "test_exit_code": 0})
    many = _synth({"tool_errors": 500, "test_exit_code": 0})
    assert few["score"] == pytest.approx(many["score"])
    zero = _synth({"tool_errors": 0, "test_exit_code": 0})
    assert zero["score"] > few["score"]


def test_absent_signals_are_not_scored_as_zero():
    """A host that cannot report a signal must not be punished for it.

    Treating absence as failure would make every delegated run look bad and would
    make `mass` stop meaning coverage.
    """
    with_build = _synth({"test_exit_code": 0, "build_exit_code": 0})
    without_build = _synth({"test_exit_code": 0})
    assert with_build["score"] == pytest.approx(without_build["score"])
    assert "build_exit_code" in without_build["absent"]
    assert "build_exit_code" in with_build["present"]


def test_expected_files_are_matched_as_a_fraction_against_what_changed():
    half = _synth({"expected_files": ["src/a.py", "src/b.py"], "diff": [{"file": "src/a.py"}]})
    assert half["signals"]["files_changed"] == ["src/a.py"]
    whole = _synth({"expected_files": ["src/a.py"], "diff": [{"file": "src/a.py"}]})
    assert whole["score"] > half["score"]


def test_an_empty_expected_files_list_is_absent_not_perfect():
    """No requirement stated is not the same as every requirement met."""
    result = _synth({"expected_files": [], "test_exit_code": 0})
    assert "expected_files" in result["absent"]


# ── the one signal that must never matter ──────────────────────────────
def test_the_models_own_prose_is_read_but_never_changes_the_score():
    """`response_summary` is the defect this phase exists to close.

    Rewarding markdown headers and Chinese function words is what made every
    delegated run score identically; the field is echoed back so a reviewer can
    see it, and weighted at zero so it cannot influence the verdict.
    """
    confident = _synth({"test_exit_code": 0, "response_summary": "# Done\n- all tests pass"})
    terse = _synth({"test_exit_code": 0, "response_summary": ""})
    assert confident["score"] == pytest.approx(terse["score"])
    assert confident["confidence"] == pytest.approx(terse["confidence"])
    assert "response_summary" in confident["signals"]
    assert DEFAULTS["weights"]["response_summary"] == 0.00


def test_an_unreported_diff_is_absent_rather_than_a_free_signal():
    """The old behaviour: every run got diff weight because an empty list looked
    like a reported signal, which quietly raised mass for loops that changed
    nothing and let 5% of coverage steer a verdict."""
    result = _synth({"test_exit_code": 0})
    assert "diff" in result["absent"]
    assert result["mass"] == pytest.approx(0.45)


def test_changed_files_the_engine_observed_count_as_a_reported_diff():
    result = _synth({}, {"files_changed": ["src/a.py"]})
    assert "diff" in result["present"]
    assert result["signals"]["files_changed"] == ["src/a.py"]


def test_min_verdict_mass_is_read_from_the_shipped_defaults():
    """A synthesizer key that the default policy lacks would crash every loop, and
    one the tests supply but the engine lacks means the tests tune nothing."""
    defaults = load_policy("outcome")
    assert set(DEFAULTS) == set(defaults)
    assert DEFAULTS["weights"] == defaults["weights"]
    assert defaults["weights"]["response_summary"] == 0.00


def test_prose_alone_cannot_produce_a_verdict():
    result = _synth({"response_summary": "I completed the refactor successfully"})
    assert result["score"] is None
    assert result["outcome"] == "partial"
    assert result["needs_review"] is True


# ── a delegated run with no signals ────────────────────────────────────
def test_nothing_reported_is_partial_not_a_lie_either_way():
    """The engine does not know, so it says it does not know and asks a human."""
    result = _synth({})
    assert result["outcome"] == "partial"
    assert result["quality_score"] == 0.0
    assert result["confidence"] == 0.0
    assert result["needs_review"] is True
    assert result["synthesised"] is True


def test_a_zero_confidence_run_is_not_auto_labelled_success_and_so_never_reinforces():
    """quality 0.0 sits under every promotion threshold, which is the point."""
    result = _synth({})
    assert result["quality_score"] < DEFAULTS["thresholds"]["partial"]


# ── policy override plumbing ───────────────────────────────────────────
def test_weight_overrides_take_effect_without_a_code_change():
    """`content/policies/outcome.json` is the tuning surface, so it must be real."""
    muted = synthesize(
        {"test_exit_code": 1, "todos_unfinished": 0},
        engine_evidence={},
        policy={**DEFAULTS, "weight_overrides": {"test_exit_code": 0.0}},
    )
    assert muted["outcome"] != "failure"
    assert "test_exit_code" in muted["present"]


def test_min_auto_confidence_is_respected():
    signals = {"test_exit_code": 0}
    assert _synth(signals, min_auto_confidence=0.30)["needs_review"] is False
    assert _synth(signals, min_auto_confidence=0.90)["needs_review"] is True


def test_reasons_explain_the_verdict_in_the_order_that_matters():
    reasons = _synth({"user_interrupted": True, "test_exit_code": 0})["reasons"]
    assert reasons[0] == "user_interrupted"
    assert any("test_exit_code" in reason for reason in reasons)


def test_synthesis_is_deterministic():
    """Same signals, same verdict — a learning signal that jitters is useless."""
    a = _synth({"test_exit_code": 0, "tool_errors": 2, "diff": [{"file": "a"}]})
    b = _synth({"test_exit_code": 0, "tool_errors": 2, "diff": [{"file": "a"}]})
    assert a == b


def test_the_trace_survives_the_synthesis_echo():
    """A trajectory that is dropped on its way through synthesis is a trajectory that never happened.

    The contract and the synthesiser keep **two independent lists** (`SIGNAL_FIELDS` and `_SIGNALS`), and the
    echo keeps only the latter: a key declared in one place is silently discarded before the store ever sees
    it. The method-level lesson lives or dies on that echo, so the coupling is pinned here rather than left
    to whoever adds the next signal.
    """
    trace = [
        {"n": 1, "tool": "bash", "method": "pytest", "exit": 1},
        {"n": 2, "tool": "bash", "method": "python -m pytest", "exit": 0},
    ]
    result = _synth({"tool_trace": trace, "tool_calls": 2, "test_exit_code": 0})
    assert result["signals"].get("tool_trace") == trace, "the ordered attempts must survive verbatim"
    assert result["signals"].get("tool_calls") == 2, "the denominator is what makes the failures countable"


def test_a_trajectory_buys_no_verdict_confidence():
    """The trajectory is material for a reviewer, never evidence in a verdict — the `response_summary` rule.

    If reporting attempts raised `mass`, a run that flailed its way to success would look *more* certain than
    one that went straight through, and the gate would learn to trust thrashing.
    """
    bare = _synth({"test_exit_code": 0})
    with_trace = _synth({
        "test_exit_code": 0,
        "tool_trace": [{"n": i, "tool": "bash", "method": "pytest", "exit": 1} for i in range(1, 6)],
        "tool_calls": 5,
    })
    assert with_trace["mass"] == bare["mass"], "an unweighted signal cannot add coverage"
    assert with_trace["confidence"] == bare["confidence"]
    assert with_trace["outcome"] == bare["outcome"]
    assert with_trace["score"] == bare["score"]
