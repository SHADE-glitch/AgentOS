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

### D-003 · 2026-10-15 · chore
Symptom  The two READMEs opened straight into their own prose: a first-time reader met the idea,
         the research note and the snapshot warning before being told, in one place, what the
         repository is, what it replaces and how to run it. Those four answers existed — scattered
         between the hero note and Quick start — and had to be assembled by hand.
Change   Both `README.md` and `README.zh-CN.md` open with the four-part house opening the
         machine-wide standard asks for — **What it is** / **What it solves** / **How to run** /
         **Where to look**, and **是什么** / **解决什么** / **怎么跑** / **去哪看** — placed after
         the title and badges and before the repository's own prose. Nothing below the four items
         moved; the switcher, the title and the badges are untouched.
Evidence 2026-10-15 local: `python3 -m pytest tests/test_readme_bilingual.py tests/test_conventions.py`
         17 passed, run with the final content of this entry in the tree. Each of the four items was
         distilled from text already in the READMEs (the hero summary and Quick start), not invented.
Cost     None to runtime behaviour — documentation only.

### D-004 · 2026-10-15 · chore
Symptom  `STANDARD.md` §1 named two `AGENTS.md` sections (`Hard rules`, `Docs & commits`), but the
         nine sibling dimension-A repositories also carry a third, `## Recording conventions` — the
         repository's own additions to the shared `CHANGELOG` rules. This repository carried neither
         the heading nor a place for those additions, so its record-writing rules lived only in the
         `CHANGELOG` header.
Change   Add `## Recording conventions` to `AGENTS.md`, between `## Delivery cadence` and
         `## Listed on the GitHub profile`. Its four bullets are distilled from rules already in this
         repository — the "no coverage gate" note in `CHANGELOG.md`, the `feat` exclusion, the
         "fetch numbers live, never reuse a remembered value" rule, and the privacy line (counts and
         key names, never raw values). No new rule is introduced and no code is touched.
         `STANDARD.md` §1 was amended in the same round to name this section as dimension A's third.
Evidence 2026-10-15 local: `python3 -m pytest tests/test_conventions.py tests/test_readme_bilingual.py`
         17 passed, run with the final content of this entry in the tree; the layout guard does not
         list `Recording conventions` among the standard's own headings, so the new section does not
         trip it.
Cost     Documentation only; the heading is descriptive and is not itself a gate. The four bullets
         restate rules that already lived in `CHANGELOG.md`, kept short so they do not become a second
         source of truth.

### D-005 · 2026-10-16 · chore
Symptom  The pointer in AGENTS.md is followed only by an agent that chooses to; nothing made the
         standard reach the context, and the section list had drifted — §5 (the conflict rule) was
         missing.
Change   End the pointer block with two bare `@` imports and add `opencode.json` naming the same two
         files in its `instructions` array; add `§5 conflict rule`. `tests/test_conventions.py`'s
         `ROOT_FILES` gains `opencode.json`.
Evidence 2026-10-16: CodeBuddy CLI with every tool disabled printed the tokens the imports carried;
         opencode `run` printed the token its `instructions` named, with no tool call.
         `python3 -m pytest tests/test_conventions.py -q` 9 passed.
Cost     Both hooks name `~/.agents`, absent in another clone, so they are skipped there — the
         pointer stays the portable part.

### D-006 · 2026-10-19 · chore

Symptom  Four places claimed "502 passed" while python3 -m pytest collects and passes 513;
         docs/audit/current-state.md still described v4 / 13 memories as the present state.
Change   The badge, both READMEs and AGENTS.md now say 513, and test_readme_bilingual.py pins
         513 so the pair cannot drift. The audit snapshot carries a banner: it is a 2026-09-30
         reading, current values come from ./bin/aos doctor --json.
Evidence 2026-10-19: python3 -m pytest 513 passed; tests/test_readme_bilingual.py passes with
         the updated pin.
Cost     The banner leaves the historical numbers in place instead of rewriting them.
Commit   b682430

### D-007 · 2026-10-19 · fix

Symptom  Six table rows carried a bare `|` inside a code span — CLI flag lists (`memory add|seed|…`,
         `aos review list|label|…`), the four-value verdict (`ADD|UPDATE|DELETE|SKIP`), a telemetry
         type string (`type:text | …`), a status enum and a route pair. GFM reads a bare pipe as a
         cell separator even inside backticks, so each row rendered with extra cells.
Change   Every one of those pipes is escaped as `\|`. The rendered text is unchanged: GFM turns
         `\|` back into `|` inside the code span. No prose, number or row order was touched.
Evidence 2026-10-19: every table block in the two touched files now has a uniform pipe count;
         `python3 -m pytest` — exit 0.
Cost     None; docs only, committed on its own per AGENTS.md's doc/commit split.

Commit   d3c0c57

### D-008 · 2026-10-25 · fix

Symptom  `migrations.py` ran each version's DDL through `executescript()`, which commits the open
         transaction before the script runs. A failure halfway through left a database whose schema
         had moved while `user_version` had not, and the retry then failed permanently on the
         duplicate column — a half-migrated store with no way forward. Separately,
         `aos memory migrate --dry-run` built a `MemoryStore` before dispatching, and the
         constructor migrates, so asking to look at a plan could rebuild the database.
Change   `_execute_script` splits a script with `sqlite3.complete_statement` — semicolons inside
         string literals and comments are not separators — and runs the statements one at a time
         inside the caller's `BEGIN IMMEDIATE`. All four `executescript` sites (v2–v5) use it, and
         `ensure_baseline` is one transaction for the same reason. `_stamp` writes
         `PRAGMA user_version` and the `schema_meta` mirror together. `MemoryStore` takes
         `auto_migrate=False`, which the migrate path uses: `--dry-run` reads through
         `file:...?mode=ro` (or an in-memory empty database when the file is absent, creating
         nothing), and a real `--to` no longer gets raised to v5 by the constructor.
         `cmd_memory` dispatches migrate before any store is built.
Evidence 2026-10-25: `python3 -m pytest` — exit 0; `node --test tests/js/plugin.test.mjs` 29 pass.
         Three cases added: a failure after v3's DDL rolls back (`user_version` stays 2, no
         `confidence` column, checked again after reopening the file); `--dry-run` on a v1 index
         leaves the file's bytes and `mtime_ns` unchanged and writes no `.bak`; `--to 3` stops at
         v3. Against a `git archive` snapshot of the pre-fix tree all three go red for exactly
         those reasons.
Cost     A migration now holds the write lock for its whole length instead of releasing it between
         statements, so a concurrent writer waits or reads `database is locked`. A database left
         half-migrated by the old code is still not repaired automatically; it fails cleanly and
         rolls back. `_has_baseline` still looks at `memories` alone on purpose: tightening it
         would send an old half-built database back through the baseline and into a duplicate-index
         error.

Commit   f39cf6d
