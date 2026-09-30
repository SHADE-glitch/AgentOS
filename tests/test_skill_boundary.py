"""The four walls are boundaries, not aspirations — so they are checked.

`docs/architecture/agent-os-v2.md` §2 states them; this file fails the build when
code stops matching them. The research found every one of these projects drifting
back toward "second engine / second skill system / telemetry we also write",
usually by one small convenience that nobody re-read the boundary against.

Everything here is a grep over the repository's own source, on purpose: a rule you
can check in one second is a rule that survives a refactor.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPO_ROOT / "aos"
SELF = Path(__file__)

# Names that would mean the engine has grown a skill source, a skill writer, or a
# second telemetry surface. They are strings in this file, so this file is excluded
# from its own scan.
FORBIDDEN_NAMES = {
    "skills_dir": "the engine must not own a skills directory",
    "knowledge_dir": "knowledge belongs to basic-memory; a declared path with no reader is a decoy",
    "ENV_SKILLS_DIR": "an env var that implies Agent OS resolves skills",
    "ENV_KNOWLEDGE_DIR": "same",
    "AOS_SKILLS_DIR": "same",
    "AOS_KNOWLEDGE_DIR": "same",
    "AOS_ALLOW_SKILL_EVOLUTION": "skill evolution was decided against; a flag for it is a door left open",
    "skill_versions": "skill lifecycle belongs to the host's skill files, not to this store",
    "skill_evolution": "same",
    "skills_loaded": "a contract key with no producer; it was validated while always empty",
    "opencode run": "the engine must not drive the host; the plugin is the only entry",
}

SOURCE_FILES = [p for p in [ENGINE, REPO_ROOT / "tests"] for p in p.rglob("*.py") if p != SELF]



def _symbols(path: Path) -> set[str]:
    """Identifiers and literals this file *uses*, ignoring prose.

    Comments and docstrings deliberately do not count: the boundaries are about
    what the code can do, and a docstring explaining why a removed field stayed
    removed is not a re-introduction of it. String literals do count, because an
    environment variable or a subprocess argument lives there.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.add(node.value)
    return found


def _hits(name: str, files: list[Path]) -> list[str]:
    phrase = " " in name
    offenders = []
    for path in files:
        for symbol in _symbols(path):
            matched = (phrase and name in symbol) or (not phrase and symbol == name)
            if matched:
                offenders.append(str(path.relative_to(REPO_ROOT)))
                break
    return sorted(set(offenders))


def _engine_and_tests() -> list[Path]:
    return [p for p in SOURCE_FILES if not _is_doc_only(p)]


def _is_doc_only(path: Path) -> bool:
    return False


# Names that are also banned in tests, because their appearance anywhere means
# the door exists. The rest are allowed in `tests/`: a test that asserts
# `"skills_loaded" not in doc["skill"]` is pinning a removal, and forbidding that
# would push us toward deleting the very guard that keeps it gone.
_DOOR_NAMES = {"AOS_SKILLS_DIR", "AOS_KNOWLEDGE_DIR", "AOS_ALLOW_SKILL_EVOLUTION", "opencode run"}
ENGINE_ONLY = [p for p in SOURCE_FILES if p.is_relative_to(ENGINE)]
EVERYWHERE = SOURCE_FILES


def test_no_skill_source_or_skill_writer_anywhere():
    offenders = []
    for name, reason in FORBIDDEN_NAMES.items():
        scope = EVERYWHERE if name in _DOOR_NAMES else ENGINE_ONLY
        found = _hits(name, scope)
        if found:
            offenders.append(f"{name} ({reason}): {', '.join(found[:4])}")

    assert offenders == [], "; ".join(offenders)


def test_engine_never_shells_out_to_the_host():
    """`opencode run` split across argv items would slip past a phrase match.

    Checked structurally instead: no `subprocess` call in the engine may pass the
    host binary as an argument. This is the wall that P1 cut `adapters/opencode.py`
    on, and a new provider that drives opencode is the shape of a regression here.
    """
    hits = []
    for path in ENGINE_ONLY:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", "") or getattr(func, "id", "")
            if name not in {"run", "Popen", "call", "check_output", "check_call"}:
                continue
            rendered = ast.dump(node)
            if '"opencode"' in rendered or "'opencode'" in rendered:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert hits == [], (
        "the plugin is the only entry point; the engine may not invoke the host: " + ", ".join(hits)
    )


def test_engine_never_touches_a_skill_file():
    """No SKILL.md read, and certainly no write — skill lifecycle is the host's."""
    hits = []
    for path in SOURCE_FILES:
        if not path.is_relative_to(ENGINE):
            continue
        for symbol in _symbols(path):
            for needle in ("SKILL.md", "personal-skills", "skill_stats", "skill-stats"):
                if needle in symbol:
                    hits.append(f"{path.relative_to(REPO_ROOT)}: {needle}")

    assert hits == [], (
        "skill telemetry and skill files belong to the installed tracker and the host; "
        "read-only integration happens outside the core engine: " + ", ".join(sorted(set(hits)))
    )


def test_content_dir_ships_no_skills_directory():
    assert not (REPO_ROOT / "content" / "skills").exists(), (
        "content/skills/ was deleted as a second skill source; recreating it re-opens the wall"
    )


def test_nothing_claims_to_modify_business_code():
    """`auto_modify_code` may exist as a documented constant, and only as False."""
    offenders = []
    for path in SOURCE_FILES:
        if not path.is_relative_to(ENGINE):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "AUTO_MODIFY_CODE":
                        value = node.value
                        if not (isinstance(value, ast.Constant) and value.value is False):
                            offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert offenders == [], f"auto-modifying business code is a boundary, not a default: {offenders}"


def test_no_write_path_outside_the_store_is_declared_in_the_engine():
    """`~/.config/opencode/**` must stay unwritable, including by constant path.

    Checked as literals because the ban's whole point is that it holds without
    runtime cooperation: no host-owned directory may appear in the engine as a
    path it could open for writing.
    """
    hits = []
    for path in SOURCE_FILES:
        if not path.is_relative_to(ENGINE):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"[\"'~].{0,20}\.config/opencode", line) and "Path.home" in line:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{i}")

    assert hits == [], (
        "the engine must never name a host-owned directory as a target; reading it is allowed, "
        "holding a path to it is how a later 'temporary' write starts: " + ", ".join(hits)
    )
