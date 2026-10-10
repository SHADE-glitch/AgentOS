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
