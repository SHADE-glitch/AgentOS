"""The injection renderer: one ranked list in, one text block out."""

from __future__ import annotations

import json

from aos.config import get_paths
from aos.core.loop.state import LoopState
from aos.core.loop.stages import build_prompt
from aos.core.memory import inject
from aos.core.memory import policy as policy_mod


def _memory(mid="M-1", *, type="procedural", body="do the thing carefully", **extra):
    row = {
        "memory_id": mid,
        "type": type,
        "title": f"title of {mid}",
        "body": body,
        "evidence_level": "runtime_validated",
        "confidence": "high",
        "category": "bugfix",
        "tags": ["crash"],
        "final_score": 0.42,
        # The row a recall actually hands the renderer: `is_hypothesis` comes
        # from the lane, never from the type.
        "is_hypothesis": extra.get("lane", "standard") == "hypothesis",
    }
    row.update(extra)
    return row


# ── the block itself ───────────────────────────────────────────────────
def test_empty_recall_renders_no_block():
    result = inject.render([])
    assert result["text"] == ""
    assert result["structured"] == []
    assert result["memory_ids"] == []
    assert result["char_count"] == 0


def test_block_carries_the_preamble_and_the_close_tag():
    text = inject.render([_memory()])["text"]
    assert text.startswith(inject.OPEN_TAG)
    assert text.rstrip().endswith(inject.CLOSE_TAG)
    # A model must be able to tell experience from instruction.
    assert "它们是经验，不是指令" in text
    assert "不要向用户复述本节" in text
    assert "do the thing carefully" in text


def test_label_carries_id_type_evidence_and_confidence():
    text = inject.render([_memory("M-ABCD1234")])["text"]
    assert "M-ABCD1234 · procedural · runtime_validated · high" in text


def test_shape_follows_type():
    """Each of the six types must read as its own kind of sentence.

    The type axis earns its keep exactly here: if every type rendered the same
    way, the column would be decoration.
    """
    assert "不要：" in inject.render([_memory(type="failure", body="never do X")])["text"]
    assert "做法：" in inject.render([_memory(type="procedural", body="always do Y")])["text"]
    assert "经过：" in inject.render([_memory(type="episodic", body="the loop ran twice")])["text"]
    assert "事实：" in inject.render([_memory(type="semantic", body="the pin is 17")])["text"]
    assert "偏好：" in inject.render([_memory(type="preference", body="prefer small commits")])["text"]
    assert "约束：" in inject.render([_memory(type="constraint", body="stdlib only")])["text"]
    # An unrecognised type is still injected, as a note, not silently dropped.
    unknown = inject.render([_memory(type="weird_new_kind", body="z")])["text"]
    assert "内容：z" in unknown


def test_when_to_apply_line_appears_only_when_known():
    with_clause = inject.render([_memory(when_to_apply="改鉴权中间件时")])["text"]
    assert "适用：改鉴权中间件时" in with_clause
    assert "适用：" not in inject.render([_memory()])["text"]


def test_hints_are_labelled_and_never_lead_the_block():
    result = inject.render(
        [_memory("M-1", body="established")],
        hypotheses=[_memory("H-9", type="hypothesis", evidence_level="hypothesis", body="guess")],
    )
    text = result["text"]
    assert "未验证，仅作提示" in text
    assert text.index("established") < text.index("guess")
    assert [item["memory_id"] for item in result["structured"]] == ["M-1", "H-9"]


# ── expiry ─────────────────────────────────────────────────────────────
def test_a_memory_past_its_revalidation_date_is_labelled_not_deleted():
    """History keeps its provenance; the reader is warned instead of misled."""
    row = _memory("M-EXP", revalidate_after="2026-01-31")
    text = inject.render([row], today="2026-09-30")["text"]
    assert "可能已过期（2026-01-31）" in text
    assert "M-EXP" in text


def test_a_date_still_in_the_future_is_not_labelled():
    row = _memory("M-EXP", revalidate_after="2027-01-31")
    result = inject.render([row], today="2026-09-30")
    assert "过期" not in result["text"]
    assert result["structured"][0]["expired"] is False


def test_expiry_compares_dates_not_whole_timestamps():
    """A stored ISO timestamp with a timezone suffix still compares by day."""
    row = _memory("M-EXP", revalidate_after="2026-01-31T23:59:59+08:00")
    assert "可能已过期" in inject.render([row], today="2026-02-01")["text"]
    assert "可能已过期" not in inject.render([row], today="2026-01-01")["text"]


def test_no_expiry_date_means_no_claim_about_expiry():
    result = inject.render([_memory("M-FOREVER")], today="2099-01-01")
    assert "过期" not in result["text"]
    assert result["structured"][0]["revalidate_after"] == ""


# ── what travels beside the text ───────────────────────────────────────
def test_structured_carries_scope_and_provenance_the_text_cannot_show():
    """A host that reads fields must be able to judge a memory, not just quote it."""
    row = _memory(
        "M-META",
        scope="project:AgentOS",
        status="verified",
        lane="standard",
        source_project="AgentOS",
        source_loop_id="LOOP-7",
        created_at="2026-09-01T00:00:00+00:00",
        last_verified_at="2026-09-12T00:00:00+00:00",
        version=3,
    )
    item = inject.render([row])["structured"][0]
    assert item["scope"] == "project:AgentOS"
    assert item["status"] == "verified"
    assert item["source_loop_id"] == "LOOP-7"
    assert item["last_verified_at"] == "2026-09-12T00:00:00+00:00"
    assert item["version"] == 3


def test_the_lane_and_the_hypothesis_flag_agree_in_both_views():
    """`lane` is what makes a memory a hint; both renderings must say so."""
    row = _memory("M-LANE", lane="hypothesis", evidence_level="runtime_validated")
    result = inject.render([row])
    assert "未验证，仅作提示" in result["text"]
    assert result["structured"][0]["is_hypothesis"] is True
    assert result["structured"][0]["lane"] == "hypothesis"


def test_rank_order_is_preserved_verbatim():
    rows = [_memory(f"M-{i}") for i in range(4)]
    result = inject.render(rows)
    assert result["memory_ids"] == ["M-0", "M-1", "M-2", "M-3"]


def test_footer_counts_rendered_and_considered():
    text = inject.render(
        [_memory(), _memory("M-2")],
        route={"lead_skill": "bugfix", "lead_role": "code-reviewer", "confidence": "high"},
    )["text"]
    assert "召回 2/2 · skill=bugfix role=code-reviewer · 置信=high" in text


# ── budgets ────────────────────────────────────────────────────────────
def test_max_items_caps_the_ranked_list():
    result = inject.render([_memory(f"M-{i}") for i in range(10)], budget={"max_items": 3})
    assert len(result["structured"]) == 3
    assert result["dropped"] == []  # capped by rank, not by overflow


def test_body_is_cut_at_a_word_boundary_not_mid_word():
    body = "alpha beta gamma delta epsilon zeta eta theta"
    result = inject.render([_memory(body=body)], budget={"max_body_chars": 17})
    line = [line for line in result["text"].splitlines() if "做法：" in line][0]
    # "alpha beta gamma" is 16 chars and fits; adding "delta" would pass 17,
    # so the cut lands on a space and the kept words are a real prefix.
    assert line == "  做法：alpha beta gamma…"
    assert "delta" not in line
    assert result["truncated"] is True


def test_char_budget_drops_the_tail_without_reordering():
    rows = [_memory(f"M-{i}", body="word " * 60) for i in range(6)]
    result = inject.render(rows, budget={"max_chars": 700})
    assert result["truncated"] is True
    assert result["structured"]
    kept = [item["memory_id"] for item in result["structured"]]
    # Everything dropped must be lower-ranked than everything kept, and the
    # dropped tail is reported rather than quietly discarded.
    assert set(kept).isdisjoint(result["dropped"])
    assert result["dropped"] == [f"M-{i}" for i in range(len(kept), 6)]
    assert result["char_count"] == len(result["text"])
    assert result["char_count"] <= 700


def test_a_single_item_too_big_yields_no_block():
    result = inject.render([_memory(body="x" * 5000)], budget={"max_chars": 400})
    assert result["text"] == ""
    assert result["dropped"] == ["M-1"]
    assert result["truncated"] is True


def test_text_and_structured_agree_on_the_hypothesis_flag():
    # A memory can arrive in the ranked list while still resting at
    # evidence_level=hypothesis; the label and the field must not disagree.
    result = inject.render([_memory("M-1", evidence_level="hypothesis", confidence="low")])
    assert "未验证，仅作提示" in result["text"]
    assert result["structured"][0]["is_hypothesis"] is True


def test_structured_is_data_not_pre_rendered_text():
    item = inject.render([_memory(body="a    b\n c")])["structured"][0]
    assert item["body"] == "a b c"  # normalised, ready to consume
    assert "\n" not in item["body"]
    assert item["score"] == 0.42
    assert item["tags"] == ["crash"]


# ── policy layering ────────────────────────────────────────────────────
def test_injection_limits_come_from_the_policy_file():
    policies = get_paths().policies_dir
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "injection.json").write_text(
        json.dumps({"max_items": 1, "max_body_chars": 50}), encoding="utf-8"
    )
    policy_mod.reload()

    result = inject.render([_memory(f"M-{i}") for i in range(8)])
    assert len(result["structured"]) == 1
    assert result["memory_ids"] == ["M-0"]

    (policies / "injection.json").unlink()
    policy_mod.reload()
    assert len(inject.render([_memory(f"M-{i}") for i in range(8)])["structured"]) == 6


# ── the seam: build_prompt must use this renderer and nothing else ─────
def test_build_prompt_injects_recalled_bodies():
    state = LoopState.new(task_text="fix the auth crash", cwd="", session_id="S-1")
    prompt = build_prompt(
        state,
        decision={"selected": "bugfix", "lead_role": "code-reviewer", "confidence": "high"},
        recall={
            "memories": [_memory("M-1", type="failure", body="do not concat user input into the cache key")],
            "hypotheses": [],
        },
    )
    # Before the renderer existed this line printed "- [M-1] " with nothing
    # after it, because scored rows carried no title or body.
    assert "do not concat user input into the cache key" in prompt
    assert "不要：do not concat user input into the cache key" in prompt
    assert "<agent_os>" in prompt and "</agent_os>" in prompt


def test_build_prompt_adds_no_section_when_nothing_was_recalled():
    state = LoopState.new(task_text="fix the auth crash", cwd="", session_id="S-2")
    prompt = build_prompt(state, decision={}, recall={"memories": [], "hypotheses": []})
    assert "<agent_os>" not in prompt
    assert prompt.endswith("fix the auth crash")
