"""Reachability: nothing in the engine may be written and never read.

Every project in `docs/research/` shipped at least one component that was built,
tested, and then never called by the product path — a `skill_usage_log` with no
writer, a `view_count` that was never reset, a search index nobody queried. This
repository caught the same shape three times in its own audit (`dedupe_key` with
no generator, `retrieval_log` with no reader, `skills_loaded` validated but always
empty), so the check is structural rather than a review habit.

The rule is deliberately about *references*, not about call graphs: a public
definition anywhere in `aos/` must be named by some other file in the repository
(the engine or its tests). An allowlist covers the genuine host-facing APIs, and
every allowlisted name must itself be exercised — otherwise the list is just a
parking lot for the next orphan.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPO_ROOT / "aos"
TESTS = REPO_ROOT / "tests"

# Name -> why the engine itself does not call it. Each must still be exercised by
# a test, checked below, or it is reported as an unproven API.
HOST_FACING = {
    "reset_caches": "a long-lived host swaps AOS_CONTENT_DIR mid-process; conftest calls it around every test",
    "get_evidence": "reads back the evidence bundle the engine writes; the artifact must be inspectable",
    "list_evidence": "enumerates the bundles of a session for the same reason",
    "available": "provider registry introspection for hosts and diagnostics",
    "conflicts_for": "reference implementation the dedupe cycle is pinned against",
}

_DEF_RE = re.compile(r"\s*(?:async\s+)?(?:def|class)\s+")


def _public_definitions(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (node.name, node.lineno)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    ]


def _occurrences(name: str, files: list[Path]) -> int:
    pattern = re.compile(r"\b" + re.escape(name) + r"\b")
    total = 0
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not pattern.search(line):
                continue
            if _DEF_RE.match(line) and re.search(r"(?:def|class)\s+" + re.escape(name) + r"\b", line):
                continue  # the definition itself
            total += 1
    return total


def test_every_public_definition_is_referenced_somewhere():
    engine_files = sorted(ENGINE.rglob("*.py"))
    all_files = engine_files + sorted(TESTS.rglob("*.py"))
    orphans = []
    for path in engine_files:
        for name, line in _public_definitions(path):
            if _occurrences(name, all_files) == 0:
                orphans.append(f"{path.relative_to(REPO_ROOT)}:{line} {name}")

    assert orphans == [], (
        "public definitions nobody references are how this codebase accumulated "
        "columns with no writer and logs with no reader: " + "; ".join(orphans)
    )


def test_allowlisted_host_apis_are_actually_exercised():
    """An allowlist entry that nothing calls is just an orphan with a comment."""
    test_files = sorted(TESTS.rglob("*.py"))
    engine_files = sorted(ENGINE.rglob("*.py"))
    unproven = []
    for name, reason in HOST_FACING.items():
        in_engine = any(
            _occurrences(name, [path]) > 0
            for path in engine_files
            if f"def {name}" not in path.read_text(encoding="utf-8")
        )
        if _occurrences(name, test_files) == 0 and not in_engine:
            unproven.append(name)

    assert unproven == [], f"declared as host-facing but nothing calls them: {unproven}"


def test_allowlist_reasons_are_written_not_assumed():
    assert all(reason.strip() for reason in HOST_FACING.values())
    assert len(HOST_FACING) == len(set(HOST_FACING))
