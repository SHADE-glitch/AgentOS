"""The two READMEs are one document in two languages, so their facts must not drift.

Splitting the entry file into English and Chinese buys readability and costs a
duplicate: the same number written twice, in two places, one of which gets edited.
This repository has been burned by exactly that shape (an aggregate left stale in a
second copy), so the shared claims are pinned rather than promised: every figure
that carries weight has to appear in **both** files, and neither file may regain a
machine identifier.

Not duplicated on purpose: the deep reference (contract field sets, the four memory
axes, lifecycle internals) lives in `README.md` alone, because a second prose copy
would be a second thing to forget to update. The Chinese file says so, and this test
pins that it says so.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EN = REPO / "README.md"
ZH = REPO / "README.zh-CN.md"

# (what it is, required text in English, required text in Chinese)
SHARED_CLAIMS = [
    ("host contract version", '"1.2"', '"1.2"'),
    ("schema version", "v5", "v5"),
    ("policy file count", "eight", "8 个"),
    ("proof: injection reached the model", "583", "583"),
    ("proof: a gate decision changed recall", "1122", "1122"),
    ("proof: the same run, after the decision", "1359", "1359"),
    ("cost: one neighbour CLI spawn", "8.1", "8.1"),
    ("budget: preflight latency", "1200", "1200"),
    ("criterion 1 threshold", "30", "30"),
    ("criterion 1 deadline", "2026-10-29", "2026-10-29"),
    ("license", "MIT", "MIT"),
    ("test suite size", "502", "502"),
    ("open defect: no run driver", "AR", "AR"),
    ("open defect: no interrupt source", "AK", "AK"),
]

PLACEHOLDERS = ["<repo>", "<subject-project>", "<rig>", "<bm-vault>", "ses_redacted"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_both_languages_exist_and_cross_link():
    assert EN.is_file() and ZH.is_file()
    assert "README.zh-CN.md" in read(EN), "the English entry must offer the Chinese one"
    assert "README.md" in read(ZH), "the Chinese entry must point back"


def test_the_chinese_file_drops_exactly_the_english_only_deep_reference():
    """The Chinese file is a deliberate subset, so this pins a *difference*, not two counts.

    The ZH entry mirrors only the decision facts; the deep reference lives in English
    alone. Pinning the gap means a section added to *both* sides keeps it and passes,
    while a section added to one side alone breaks it — the drift this catches. Today
    the two English-only sections are "The frozen contract" and "Configuration"; if a
    third is ever made English-only, update the pinned gap on purpose.
    """
    en = len(re.findall(r"^## ", read(EN), flags=re.M))
    zh = len(re.findall(r"^## ", read(ZH), flags=re.M))
    assert zh <= en, (
        f"README.zh-CN.md has {zh} '##' sections but README.md has {en} — the Chinese "
        "mirror must never carry a section the English one does not")
    assert en - zh == 2, (
        f"the English README has {en - zh} more '##' sections than the Chinese one "
        f"(README.md {en}, README.zh-CN.md {zh}); the only English-only sections are "
        '"The frozen contract" and "Configuration" — if a section was added to one side '
        "alone, add it to the other, or update this pinned gap on purpose")


def test_shared_facts_appear_in_both_files():
    en, zh = read(EN), read(ZH)
    missing = [
        f"{label}: en={want_en!r} zh={want_zh!r}"
        for label, want_en, want_zh in SHARED_CLAIMS
        if want_en not in en or want_zh not in zh
    ]
    assert missing == [], "a figure changed in one language only:\n" + "\n".join(missing)


def test_the_chinese_file_says_the_deep_reference_lives_in_english():
    """A mirror that quietly omits half the document is worse than an honest pointer."""
    assert "README.md" in read(ZH)
    assert "单一副本" in read(ZH), "state the no-duplication rule inside the file it applies to"


def test_placeholder_legend_is_identical_in_both_languages():
    en, zh = read(EN), read(ZH)
    for token in PLACEHOLDERS:
        assert token in en and token in zh, f"{token} documented in one language only"


def test_no_machine_identifier_came_back():
    """The scrub is a standing invariant, not a one-off commit."""
    for path in (EN, ZH):
        text = read(path)
        assert "/home/" not in text, f"{path.name} leaked an absolute home path"
        assert not re.search(r"ses_[0-9A-Za-z]{12,}", text), f"{path.name} leaked a host session id"
        assert "HUOSHAN" not in text, f"{path.name} named a provider environment variable"


def test_license_file_exists_and_matches_what_both_readmes_claim():
    license_path = REPO / "LICENSE"
    assert license_path.is_file(), "a public repository without a license grants nothing"
    head = read(license_path).splitlines()[0]
    assert head.startswith("MIT License")
    assert "MIT" in read(EN) and "MIT" in read(ZH)
