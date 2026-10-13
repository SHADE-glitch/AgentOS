# CHANGELOG — AgentOS

Original project, **no upstream**: nothing here is a deviation from somebody else's code, so this
record is not a divergence list. It records the repairs, the performance work, the drift guards and
the withdrawals — the things an upgrade of opencode, of the host contract, or of a neighbouring
store can invalidate.

Coverage: 83e1538..HEAD
Entries are `D-###`, monotonic, never reused; a gap is a failure, not cleanup. An entry states what
was true **as of its commit**, not current state, and aggregate counts are printed by a command,
never copied into this file. `kind` ∈ `fix | perf | taste | guard | revert | chore`.

> **No coverage gate.** Unlike the sibling tool repositories, this one has no `check:log`-style
> record-coverage checker, so nothing enforces that a code-path commit appears here. The record is
> maintained by hand; treat a missing entry as a gap to close, not as permission. Commits whose
> subject starts with `feat` are the product, not a droppable deviation, and are documented in the
> READMEs.

---

### D-001 · 2026-10-10 · chore
Symptom  This repository carried no CHANGELOG and was not listed in the machine-wide `STANDARD.md`,
         so its root-file layer, CI pinning and runtime ignore list were ungoverned.
Change   Adopt `STANDARD.md` (listed in §0); translate `AGENTS.md` to English and point it at the
         standard; add this `CHANGELOG.md` and the `MAINTENANCE.md` / `MAINTENANCE.zh-CN.md` pair;
         pin CI to the declared Python floor via a `3.11 / 3.14` matrix; add the generic `*.db`
         family to `.gitignore`.
Evidence 2026-10-10 local: `python3 -m pytest` 503 passed on Python 3.11 and on 3.14;
         `node --test tests/js/plugin.test.mjs` 29 passed.
Cost     None to runtime behaviour — docs, CI and the ignore list only.

### D-002 · 2026-10-13 · guard
Symptom  The root-file layer was a naming convention with nothing behind it. No check in this
         repository asserted that the finalized files sit at the repository root, that `LICENSE`
         exists, or that `AGENTS.md` points at the machine-wide standard instead of restating it.
         A renamed or deleted root file would only be noticed by a person reading the diff.
Change   Add `tests/test_conventions.py` (9 cases, standard library only). It asserts the finalized
         layer is present at the root and that `pyproject.toml` is the only manifest; that
         `AGENTS.md` carries the one-line dimension pointer and reproduces none of the standard's
         own numbered section headings; that `.gitignore` still covers the runtime state the
         standard lists and that `git ls-files` tracks none of it; and that no process draft is
         tracked anywhere. `AGENTS.md` gains the dimension line above the shared-standard pointer it
         already had. The file sits in `tests/`, not in `scripts/tests/`, because that is where
         this repository's suites already are and `AGENTS.md` already records the plural directory
         as its own variant of the tool convention — the suite has to be somewhere discovery
         already runs, or it is decoration. Nothing is fetched: every assertion reads this working
         tree.
Evidence `python3 -m pytest` 513 passed, and `node --test tests/js/plugin.test.mjs` 29 passed, run
         with the final content of this entry in the tree. Provoked for real: moving `LICENSE` out
         of the tree turns the root-layer case red with `AssertionError: Lists differ: [] !=
         ['LICENSE: create this file at the repository root']`, and restoring it turns the suite
         green again. Two earlier drafts of the guard were themselves red and were corrected rather
         than suppressed — a heading match that also caught this repository's own `## CI`, and an
         ignore-list spelling that only matched `.venv/` while this repository writes `.venv`.
         No test was skipped, widened or moved to make a check pass.
Cost     The manifest and ignore lists are hard-coded, so a deliberate second manifest or a new
         runtime artefact is a change to this file rather than a surprise failure. This repository
         has no record-coverage guard, so nothing checks that a production-code change reaches
         this file; that gap is D-001's, and it is recorded rather than quietly closed here.

Commit   9e40999
