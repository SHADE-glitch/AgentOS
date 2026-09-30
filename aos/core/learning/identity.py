"""Proposal identity: the same fact arriving twice must become one row.

A random id per proposal is how three failures of one task produced three
separate review rows, each needing its own human decision. Deriving the id from
what the memory *says* makes the existing reuse path (``pending_review_id``)
fire, because the second arrival asks for the id the first one already reserved.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Punctuation that carries no meaning in a fact sentence. Kept narrow on
# purpose: `/` and `-` survive inside identifiers like `cache-key` and `a/b`,
# which are part of what the fact is about.
_PUNCT = re.compile(r"[,.:;!?\u3002\uff0c\uff1a\uff1b\uff01\uff1f\u3001\uff08\uff09()\[\]{}\"']+")
_WHITESPACE = re.compile(r"\s+")
_TRAILING_NUMBER = re.compile(r"^([a-z_]+)(\d+)$")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    lowered = str(text or "").lower()
    return _WHITESPACE.sub(" ", _PUNCT.sub(" ", lowered)).strip()


def _tokens(text: str) -> list[str]:
    """Fold `java17` and `java 17` onto one token, then dedupe in order.

    Gluing a number to the word in front of it is the one equivalence worth
    computing: version facts arrive both ways from real task text. It deliberately
    does not know that `jdk 17` and `java 17` are the same fact — synonymy is the
    similarity layer's job or a human's, not a key's.
    """
    raw = text.split()
    out: list[str] = []
    index = 0
    while index < len(raw):
        token = raw[index]
        following = raw[index + 1] if index + 1 < len(raw) else ""
        if token.isalpha() and following.isdigit():
            glued = f"{token}|{following}"
            index += 2
        else:
            match = _TRAILING_NUMBER.match(token)
            glued = f"{match.group(1)}|{match.group(2)}" if match else token
            index += 1
        if glued not in out:
            out.append(glued)
    return out


def fact_key(
    *, title: str = "", body: str = "", category: str = "", mtype: str = "", scope: str = "global"
) -> str:
    """A stable key for "one fact", used to deduplicate within a scope.

    This is a lexical key, not a semantic one: it makes two spellings of the same
    wording collide, and it is honest about not knowing that `jdk 17` and
    `java 17` are one fact — that judgement is ``dedupe``'s similarity layer, or
    a human's. Sorting the tokens means word order is not treated as meaning.
    """
    subject = normalize(f"{title} {body}")
    tokens = "|".join(sorted(_tokens(subject)))
    return f"{scope}|{mtype}|{normalize(category)}|{tokens}"


def stable_id(key: str, *, prefix: str = "M") -> str:
    """`M-XXXXXXXX` from a fact key, uppercase to match the rest of the ids."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest.upper()}"


def proposal_id(*, scope: str, category: str, mtype: str, title: str, body: str) -> str:
    """The id a run's episode memory would keep, so retries do not pile up."""
    return stable_id(fact_key(title=title, body=body, category=category, mtype=mtype, scope=scope))
