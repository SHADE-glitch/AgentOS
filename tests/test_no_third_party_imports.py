"""Zero third-party imports is a load-bearing property, not a style preference.

The engine has no dependencies on purpose: no embedding, no network, nothing that
installs into somebody else's directory. That is what makes "disable cleanly"
true for the host — an agent OS that needs a package is an agent OS that needs a
`~/.config/opencode/**` write or a pip install to exist at all.

A rule nobody checks decays: the four projects in `docs/research/` all shipped a
storage layer that was later bypassed. This is the check that stops it here.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPO_ROOT / "aos"

_STDLIB = set(sys.stdlib_module_names)


def _top_level_modules(path: Path) -> set[str]:
    """Every module this file imports, top level, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_engine_files_are_the_thing_under_test():
    """Guards against a green suite that checked nothing."""
    files = list(ENGINE.rglob("*.py"))
    assert len(files) > 40, f"only {len(files)} engine files found under {ENGINE}"


def test_no_third_party_imports():
    offenders = []
    for path in sorted(ENGINE.rglob("*.py")):
        for module in _top_level_modules(path):
            if module in _STDLIB or module == "aos":
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}: imports {module!r}")

    assert offenders == [], (
        "the core engine must stay inside the standard library; " + "; ".join(offenders)
    )


def test_no_route_off_the_machine():
    """Network is the dependency that would redefine the project.

    No embedding, no LLM call, no fetch: an agent OS that reaches out becomes a
    client, and its data leaves the machine with it. `subprocess` is deliberately
    not banned — running git and the project's own build command is what evidence
    collection is, and validation only ever runs inside the project root the
    caller named.
    """
    forbidden_roots = {
        "http",
        "urllib",
        "ftplib",
        "smtplib",
        "xmlrpc",
        "poplib",
        "imaplib",
        "requests",
        "httpx",
        "aiohttp",
        "urllib3",
        "openai",
        "anthropic",
    }
    loopback = {"127.0.0.1", "localhost", "::1"}
    hits = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in forbidden_roots:
                    hits.append(f"{path.relative_to(REPO_ROOT)}: {name}")

        # `socket` has one legitimate use here: asking whether a service the
        # project declares is listening, on this machine. Anything more is a
        # boundary decision, so the host argument has to be a loopback literal.
        if any(getattr(node, "module", "") == "socket" or _imports_socket(node) for node in ast.walk(tree)):
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
                    continue
                if func.value.id != "socket":
                    continue
                host = node.args[0].elts[0] if node.args and isinstance(node.args[0], ast.Tuple) else None
                value = getattr(host, "value", None)
                if not (isinstance(host, ast.Constant) and value in loopback):
                    hits.append(
                        f"{path.relative_to(REPO_ROOT)}: socket.{func.attr} on a non-loopback target"
                    )

    assert hits == [], (
        "the engine may not reach off this machine; if the need is real, it is a "
        "boundary decision first: " + ", ".join(hits)
    )


def _imports_socket(node) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == "socket" for alias in node.names)
    return False
