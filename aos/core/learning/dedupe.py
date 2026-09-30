"""Deciding whether a memory states a fact the store already holds.

Three layers, cheapest first, because "same fact" is not one question:

1. **fact key** (:mod:`.identity`) — two spellings of one wording. Deterministic,
   indexed by ``uq_mem_dedupe``, and honest about only being lexical.
2. **similarity** — ``difflib.SequenceMatcher`` on the normalised text, with tag
   overlap as corroborating evidence. Stdlib only; no embeddings, by constraint.
3. **the grey band** — the ratio says "probably the same" but not certainly. That
   is handed to a person, because a false merge loses a fact nobody agreed to
   lose, and a false split only costs a second look.

Only :func:`classify` is meant to be called from outside; the rest are its parts.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Optional

from aos.core.learning.identity import fact_key, normalize

# Ratio at or above which two rows are treated as one fact.
MERGE_AT = 0.86
# Ratio at or above which they are similar enough to be worth a human question.
GREY_AT = 0.60
# A memory in one of these states is not competing for the same fact: it has
# already been retired or replaced, so a new row may legitimately restate it.
_INACTIVE_STATUSES = frozenset({"superseded", "invalidated", "archived", "deprecated"})


def text_of(memory: dict[str, Any]) -> str:
    """The claim itself: the title, falling back to the body when there is none.

    Similarity is measured on the title because the title *is* what a memory
    asserts — it is capped at one line and is the first thing injected. Mixing in
    the body would compare prose, and for a proposal the body is a template
    ("任务「…」的结果：failure。") that repeats the title and drags every ratio
    down: measured on this store's own text, title+body scoring tops out near 0.24
    for a restatement a human would call the same fact, while titles separate
    0.34 / 0.60 / 1.00 the way the bands intend. Exact duplication is still caught
    by the fact key, which does include the body.
    """
    title = normalize(memory.get("title") or "")
    return title or normalize(memory.get("body") or "")


def tags_of(memory: dict[str, Any]) -> set[str]:
    return {str(t).strip().lower() for t in (memory.get("tags") or []) if str(t).strip()}


def tag_jaccard(a: dict[str, Any], b: dict[str, Any]) -> float:
    left, right = tags_of(a), tags_of(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
    ta, tb = text_of(a), text_of(b)
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


def similarity(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Both numbers a reviewer would want, not a single opaque score."""
    text_ratio = ratio(a, b)
    overlap = tag_jaccard(a, b)
    return {"ratio": round(text_ratio, 3), "tag_jaccard": round(overlap, 3)}


def compares_to(store: Any, memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Existing memories that could be the same fact: same scope, still live.

    Same scope is not a convenience. A fact about one repository is not a second
    opinion about another, and comparing across scopes is how Java advice starts
    competing with JavaScript advice.
    """
    scope = str(memory.get("scope") or "global")
    skip_id = str(memory.get("memory_id") or "")
    rows = []
    for row in store.memories_for_scoring(scopes=[scope]):
        if row["memory_id"] == skip_id:
            continue
        if str(row.get("status") or "") in _INACTIVE_STATUSES:
            continue
        rows.append(row)
    return rows


def classify(
    store: Any,
    memory: dict[str, Any],
    *,
    merge_at: float = MERGE_AT,
    grey_at: float = GREY_AT,
) -> dict[str, Any]:
    """`new` / `merge` / `review`, with the numbers the decision rests on.

    ``review`` is the grey band: similar enough that one of the two is probably
    wrong, not similar enough to act without asking. A false merge silently
    deletes a fact; a false review costs one look.

    Tag overlap is *reported* alongside the ratio but never acts on it. Two rows
    about the same subject that say different things — "normalise the input" and
    "add a namespace prefix", both tagged ``cache`` — are exactly the pair a human
    has to decide, and letting tag agreement promote a grey ratio into a merge
    would delete one of them without asking.
    """
    best: Optional[dict[str, Any]] = None
    for other in compares_to(store, memory):
        scores = similarity(memory, other)
        if best is None or scores["ratio"] > best["scores"]["ratio"]:
            best = {"match": other, "scores": scores}
    if best is None:
        return {"action": "new", "match": None, "scores": {"ratio": 0.0, "tag_jaccard": 0.0}}

    score, overlap = best["scores"]["ratio"], best["scores"]["tag_jaccard"]
    matched = best["match"]
    if score >= merge_at:
        why = "ratio"
        return {
            "action": "merge",
            "match": {
                "memory_id": matched["memory_id"],
                "title": matched.get("title", ""),
                "status": matched.get("status", ""),
                "ratio": score,
                "tag_jaccard": overlap,
                "by": why,
            },
            "scores": {"ratio": score, "tag_jaccard": overlap},
        }
    if score >= grey_at:
        return {
            "action": "review",
            "match": {
                "memory_id": matched["memory_id"],
                "title": matched.get("title", ""),
                "status": matched.get("status", ""),
                "ratio": score,
                "tag_jaccard": overlap,
                "by": "grey band",
            },
            "scores": {"ratio": score, "tag_jaccard": overlap},
        }
    return {"action": "new", "match": None, "scores": {"ratio": score, "tag_jaccard": overlap}}


def key_for(memory: dict[str, Any]) -> str:
    """The dedupe key a row should carry, derived from what it says.

    Lives here so every writer (authoring, seeding, an approved proposal) reaches
    for the same normalisation, and the ``uq_mem_dedupe`` index stops being a
    constraint on an always-empty column.
    """
    return fact_key(
        title=str(memory.get("title") or ""),
        body=str(memory.get("body") or ""),
        category=str(memory.get("category") or ""),
        mtype=str(memory.get("type") or ""),
        scope=str(memory.get("scope") or "global"),
    )
