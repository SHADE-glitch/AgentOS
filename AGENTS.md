# AGENTS.md — the non-negotiable checks in this repository

Guidance for AI coding agents working in this repository. This repository is public.

> **Shared standard.** Root file names, the process-draft location (`docs/reports/`), the
> `CHANGELOG` entry format, CI version pinning and entry commands, the test entry command, and
> the runtime ignore list are defined once in the machine-wide `STANDARD.md` (outside this
> repository) and are not restated here.
>
> **Push over SSH, never HTTPS.** Verify `git remote get-url --push origin` starts with `git@`
> before pushing; if it starts with `https://`, fix it first — never push over HTTPS.
>
> **Test entry (project-specific variant of the standard's tool convention).** Tests live in
> `tests/` (not `scripts/tests/`) and run with `python3 -m pytest`; the JS plugin tests run with
> `node --test tests/js/plugin.test.mjs`.
>
> **Language.** `docs/**` is Chinese by design — a project-specific exception to the standard's
> "English outside the whitelist" rule. Everything else (code, comments, CLI/TUI text, every
> other `.md`) is English.

Target `<repo>`, treated as a **public repository** (`github.com/SHADE-glitch/AgentOS`): every privacy line is enforced as if public, regardless of where the visibility switch sits right now.
In the docs, `<repo> / <subject-project> / <rig> / <bm-vault> / ses_redactedNN` are redaction placeholders; the glossary is at the end of `README.md` under "Privacy and placeholders". Redact before publishing, and re-run the two test commands after redacting.
It is opencode's **external evidence and governance layer**: real run → synthesized verdict → human gate → promote/demote → next recall changes behavior.
The engine is pure-stdlib Python; the host enters only through `bin/aos` + a stdin/stdout JSON contract; the engine never calls opencode.
This file also governs the case of "developing this repository with another AI agent (e.g. qoder cn)".

**The first priority is "prove it is worth using every day", not "add another layer".** New features are off by default; before adding a module you must be able to point to a column of "nobody implements this" in `docs/research/open-source-capability-matrix.md`. Keep-or-kill is decided by a criterion (`docs/decision/positioning.md §6`): within 4 weeks of power-on, if real runs with `source='hot'` < 30 ⇒ stop adding features.
**Current state and aggregate numbers are not hard-coded here** — always fetch them live with `./bin/aos doctor --json`; never reuse last round's remembered values.

Details, evidence and defect numbers are not here: verdicts and numbers are in `docs/architecture/agent-os-v2.md` §12/§15, the execution log in `docs/plan/final-plan.md` §11, the real-machine rules in `integrations/opencode/live/README.md`.
This file holds only the "do this every time you start" shape, and every line is something that was **actually run**.

## Read before starting (especially other agents)

1. This file in full.
2. `docs/architecture/agent-os-v2.md` §12 (defect numbers) and §15 (how far something is proven, what is not).
3. `docs/plan/final-plan.md` §11 (how recent rounds went wrong and were fixed).
4. `integrations/opencode/live/README.md` (how to run on the real machine, the privacy line).

**Why**: the recurring disease of this repository is "declared but nobody wrote it / written but nobody reads it / read but it doesn't take effect / only ever run against a fixture and taken as real". The four files above are the history of these diseases; not reading them means repeating them.

## What not to do (non-goals — don't "helpfully" add them back)

- **No skill system**: do not create/read/write skill files, do not touch `personal-skills`, `content/skills/` must not be reproduced (`test_skill_boundary` blocks it). Skills belong to the host.
- **No self-built telemetry writer**: the only telemetry writer is the local skill-tracker. To consume its DB, follow the read-only rules in `final-plan §7` (list the whitelist + probe with `PRAGMA table_info` before reading + degrade if unreadable); **currently zero code** — before wiring it up, first prove it will actually change recall.
- **No MCP, no third-party dependencies** (`test_no_third_party_imports` is the enforcement). **Calling a CLI already installed on this machine via stdlib `subprocess` does not count as adding a dependency, nor as adding MCP** (owner ruling 2026-10-03; that test's docstring already excludes subprocess from the ban).
- **Do not write `~/.config/opencode/**`** (including `opencode.json`, `plugin/`, `AGENTS.md`, `skill-stats-registry.json`); the engine's **only** state write location remains `store/`. The one exception is a **one-way publish**: `review approve` writes a just-approved lesson as a note through basic-memory's own CLI (`aos/core/memory/external_write.py`) — it happens only at the moment of human-gate approval, only via the CLI, and **never opens bm's SQLite or writes its md files**; failure does not change the approval (write store first, then bm).
- **Do not make the engine something that edits code**: recovery is always plan-only, `auto_modify_code=False`.
- **No orchestration, no session retrieval, no code indexing** (conflicts with the "external brain" positioning, see `positioning.md §2/§3`).

## Non-interference is a hard constraint (explicit owner requirement)

- **Zero impact after disabling**: if `AGENT_OS_ROOT` is unset ⇒ the plugin loads but every hook no-ops, and `output.system` is **byte-for-byte identical** to not having the plugin (`tests/js/plugin.test.mjs` pins it).
- **Enhance only, never rewrite neighbors**: only push your own elements; never occupy `output.system[0]`, never edit/reorder/delete others' elements (DCP judges internal calls by `[0]`), and preserve suffixes others append into our own elements.
- **Do not touch other components' state**: do not write `~/.config/opencode/**`, do not read or write DCP / skill-tracker / notifier databases or files; apart from `existsSync`, plugin source must not import any write API.
- **Criterion 3 outranks everything**: if a capability would require writing `~/.config/opencode/**`, or editing elements others wrote into `output.system`, in order to take effect ⇒ **abandon it outright, do not discuss the benefit**.
- Disabling is two reversible actions: delete the symlink, remove `AGENT_OS_ROOT` from the alias/export.

## What counts as green

- The two READMEs (`README.md` English, `README.zh-CN.md` Chinese) **mirror only the batch of facts that decides "continue or not"**: the single deep-reference copy is the English one. Shared numbers are pinned by `tests/test_readme_bilingual.py` — change one side and it goes red, so any change to a number like "502 / 1122→1359 / 8.1–9.2s / 30 criteria / 2026-10-29" must be made on both sides (the test tells you which side you missed).
- `python3 -m pytest` and `node --test tests/js/plugin.test.mjs` — both must run; currently 502 / 29 (the rig has 15 more). Do not append a `-q` to either: `addopts` already has one `-q`, and two `-q` swallow the entire summary line (observed: `python3 -m pytest -q | grep passed` prints nothing); take the count only from `--collect-only -q`.
- Do not write `node --test tests/js/`: the directory makes it execute `fake-aos.cjs` as a test, printing `# tests 1 / # fail 1`, a false red.
- **Signals have two mutually independent lists**: the contract's `SIGNAL_FIELDS` (`aos/contract/schema.py`) and the synthesis `_SIGNALS` (`aos/core/outcome.py`). Echoing keeps only the latter ⇒ a new signal that only adds a contract key is silently dropped **before entering the store**. Adding a signal requires changing five places at once: the two lists, the default weight in `policy.py`, `content/policies/outcome.json`, the set-**equality** assertion in the seam guard (`tests/test_cli_contract.py`), and `DEFAULTS` in `tests/test_outcome.py`. Missing any one raises no error — it just does nothing (defect AJ's red screen is this).
- Criteria and thresholds come from `content/policies/*.json` (eight files: decay/external/external_write/injection/outcome/promotion/rejection/retrieval), merged by `policy.load_policy` as "built-in defaults overridden by file" ⇒ to change a threshold, change the file, don't add a local number at the call site. Adding a policy file is pinned by `tests/test_config.py`'s "every file must have a corresponding default section" (observed red screen: `external_write.json: no such policy section`); the reverse does not hold — adding only a default section without a file is **silent**.

## CI

- The only CI config is `.github/workflows/ci.yml`: triggered on `push` and `pull_request`, running on `ubuntu-latest`.
- It runs only the two local commands: `python3 -m pytest` (currently 502) and `node --test tests/js/plugin.test.mjs` (currently 29); Python on a 3.11 / 3.14 matrix (the declared floor `3.11` and the latest, per `STANDARD.md` §5), Node on 20, action versions pinned (`checkout@v4` / `setup-python@v5` / `setup-node@v4`).
- **Both must stay green**: if red, fix the code first; never make it green by skipping cases, changing assertions, or relaxing a threshold.
- CI **does not run** `./bin/aos doctor`: doctor opens a loop and leaves a pending (see "Probing the real DB is read-only"); it belongs to the human gate, not the pipeline.

**CI maintenance rules** (CI shares a source with the code, don't let it silently go stale):

- **Change CI together with the code**: a change that makes `.github/workflows/ci.yml` stale must update it **in the same commit**, not as later cleanup.
- **Adding/renaming tests does not require touching CI**: CI runs the suite commands (`python3 -m pytest` and `node --test`), which pick up new tests automatically. Only a change to **the command itself** requires editing CI.
- **Environment changes** — a new dependency, a Python/Node version bump, a new system tool needed — must update the workflow's install/prepare steps.
- **Code paths changed**: this repository currently has no "record coverage" checker; if one is introduced later (e.g. a check:log-style check against CODE_PATHS), the watched file list must be updated in sync when those files are renamed or moved, or the check stays red forever.
- **After a major refactor**, confirm CI still runs the real code and covers the changed part. A green CI that "no longer touches the changed code" is more dangerous than a red one.
- **Adding a verification layer** (headless / real machine) — explicitly decide whether CI should run it; don't add it silently.
- When what CI runs changes, this section must change too. CI is a signal, not a gate (unless branch protection is on) — glance at the result after each push.

## The shape of values passed onto the seam

- Only two legal forms: **normalize in the host process and drop the original text** (method fingerprint: keep only name-shaped tokens, ≤3 words, `-m` retained only for the interpreter, terminate the segment at any quote), or **truncate and mark the source** (`response_summary`, `session_error`).
- Raw commands, arguments, paths, env, stderr never cross the seam; `note()` keeps logging only key names/indices/counts, never values.
- A value on the seam widens the collection surface ⇒ that is the owner's decision, to be written into §12/§15 with the boundary stated, not quietly added in code.

## Probing the real DB is read-only

- `aos preflight` **opens a loop and leaves a pending** (observed: one preflight ⇒ `doctor.pending_postflight.outstanding` goes from 1 to 2) ⇒ scoring/comparison against the real DB always goes through `retrieve(query, k=5, store=MemoryStore(<db path>), log=False)`; `log=False` is the key, otherwise it writes `retrieval_log`.
- When you need the full engine path (router/scope/gate whole chain), first point `AOS_STORE_DIR` at a scratch copy — don't "just try it against the real DB".
- `retrieve()` is read-only, `compute_all_decay()` / `memory refresh` are **not**: the latter writes `decay_factor`, and writes "the lower of old and new" (a human demotion must not be raised back by recomputation) ⇒ **once lowered it can never rise again**, there is no symmetric command. Round fifteen did exactly this under the banner of a "read-only check", permanently dropping 3 real-DB seeds from 0.85 to 0.5.
- **basic-memory's DB is also read-only**: `AOS_BM_DB` (default `~/.basic-memory/memory.db`) is opened with `mode=ro` + `PRAGMA query_only=ON`, and no write statement may appear in `external.py` (`test_the_reader_issues_no_write_statement_and_leaves_the_bytes_alone` pins both the source and the file bytes). `tests/conftest.py` points it at a nonexistent tmp path ⇒ tests won't accidentally read real notes; to test recall, build a fixture DB in `tmp_path`. **Any real run/experiment is the same**: when running AOS, point all three of `AOS_STORE_DIR`/`AOS_DB_PATH`/`AOS_BM_DB` at scratch — don't use real notes as test data.
- **The only path that writes bm is a `basic-memory tool write-note` subprocess** (`external_write.py`). That "no write statement in the source" pin is only on `external.py`, so the write side pins another: `external_write.py` must not contain `sqlite3`, nor open a vault file in write mode (`test_the_engine_never_opens_the_vault_or_the_db_for_writing` pins the source, the neighbor DB bytes, and argv together). **`AOS_BM_CONFIG_DIR` is the only guardrail in conftest**: it points at a directory with no `config.json` ⇒ vault resolution fails ⇒ `skipped`, stopping before any spawn; merely swapping `AOS_BM_BIN` for a fake command is not enough (that way "command not found" pretends to be safe for us).
- **To actually run an end-to-end with basic-memory, both envs must point at scratch together**: `BASIC_MEMORY_CONFIG_DIR` (bm itself uses it to locate the config **and its `memory.db`**) and `AOS_BM_CONFIG_DIR` (the engine reads the same `config.json` to locate the vault). Setting only the latter ⇒ the neighbor's resident DB gets written. Observed: after one real CLI run on 2026-10-03, `~/.basic-memory/memory.db`'s sha and mtime were unchanged by a single character (`a090864c…`, 10-01 08:27:45). Two more neighbor facts: one CLI spawn is about **8–9 s** (the default 30s timeout is therefore a 3× margin); in a brand-new bm DB the `project` table is empty and `tool write-note` returns 404 ⇒ such a failure is merely `failed`, and the approval proceeds as before.
- `store/` has no delete command. Exiting recall has only two paths: `aos memory retire <id> --reason …` (a human types it once; no reason, no write) and the evidence ladder (5 attributable failures + 5 approvals, §12 row Z); both keep the row and the events, so "retracting a lesson" is never deleting data, it is changing state.

## Measure before writing

- Before claiming "fixed": first have a **named test that goes red**, let the red screen stand, then change the code.
- Aggregate numbers (test count, `observations.hot`, pending count, commit count) are always re-fetched by re-running the command; never reuse last round's remembered value.
- Borrowed evidence must state how far it reaches (`docs/architecture/agent-os-v2.md §1`); "I didn't hit it" must not be written as "it can't happen".
- Behavior verdicts must fix the rule **before the call** (what to grep, what threshold), not explain the result afterward.
- Any clause in the body that "must survive to the last sentence" must **reserve budget** — you can't give it the leftover space (`missing-evidence → model self-report → never delete unattributed` and the trajectory's 170-character budget are the same trick). Observed once: eight long paths pushed the remaining space negative and the whole "process" section was silently dropped.

## Re-read after editing

When `Edit`'s `old_string` anchors only one line, it swallows adjacent lines: table-row starts, paragraph sub-headings, and assignment statements have all been swallowed (rounds fourteen, fifteen, sixteen, once each, all found and restored on re-read; round sixteen swallowed the `proposed = 0` line).
After editing a markdown table/paragraph, immediately read the changed region; before changing an aggregate number, grep every occurrence first.

Automatic line-wrapping also counts as "editing": hard-wrapping by character count can cut a code span and `**` in half (`aos/core/outcome.py\n` was split in two). A wrap must land only at punctuation or between words, and the whole paragraph must be re-read after the change.

## Changing the semantics of recall and gating

- **Tightening a match must ship, in the same batch, the door by which a human can still make the thing-that-should-be-found be found** — otherwise the fix equals disappearance (AH's two halves in one batch).
- **Process narrative goes into body, not into identity**: `fact_key` consumes the whole body text ⇒ the trajectory is written into the body while the identity is computed as before, so the same thing happening a second time is "one decision", not "a new review". The key can only be computed by the **same** `fact_key` function (`test_dedupe.py` pins "the declared key equals what the store itself would derive"); spinning up another key generator is AD's disease.
- **One run produces one experience proposal**: result, process, and candidate experience are given in the same review (widening `should_propose` most easily splits it into two asks).
- Content columns (`title`/`body`/`when_to_apply`/`tags`) have exactly one writer: the author. `review approve`'s content flags are accepted only at create time, and are always rejected for an existing row; empty values are rejected before anything is written and leave no row.
- Ranking has **two independent entry points** that can both clear the 0.15 threshold (real-DB read-only observed):
  ① the router names the category — this item alone is exactly 0.15, **recall works even with zero surface overlap**, Chinese included;
  ② the surface literally hits a tag — one = 0.08 (not enough), two = 0.16 (clears the bar).
  After sanitizing the fallback bucket, the "router gave up" half of tasks has only ② left ⇒ "at least two literal tag hits" is the precondition **when the router doesn't know the topic**, not a general precondition; don't overstate it when explaining to others.
- The router's fallback bucket (`fallback`) is not a topic, it is a confession of "nothing was classified" ⇒ the query side always sanitizes it: category blanked, bucket name removed from domains/keywords, and the role that is given only on giving up is also cleared. **Only touch the query side**; a memory that genuinely talks about fallback is still found by its own tags and surface (this asymmetry is deliberate, don't "helpfully" make it both sides).

## Real-machine testing (opencode) — including the case of "another agent driving it"

- **Never use the `opencode` shell alias**: this machine's `~/.zshrc` alias injects `--auto` and an inline `AGENT_OS_ROOT`, so you can't tell which env wins, and `--auto` **auto-approves edits and arbitrary bash in the current cwd** (officially flagged dangerous). Driving the real machine always uses the absolute path `~/.opencode/bin/opencode` + an explicit `AGENT_OS_ROOT` + a **scratch-pointing `AOS_STORE_DIR`**.
- **Any test run must point the store at scratch** (`AOS_STORE_DIR` / `AOS_DB_PATH`); the real DB grows only through the owner's interactive sessions. `live/run.sh` refuses the real DB unless `AOS_RIG_ALLOW_REAL_STORE=1` and it is stated clearly.
- The model is only `opencode/space-bunny-free`; `--auto` requires owner authorization with the approval scope recorded (cwd/db/batch/model/date); zero writes to `~/.config/opencode/**`.
- Headless `opencode run` with `permission.bash=ask` and no TTY must fail the moment the model wants to call a tool ⇒ to test tool behavior you must use a real TUI (tmux-driven, method in `live/README.md`), or ask only "answerable-from-knowledge" questions; **don't fix this with `--auto`**.
- When driving the real TUI and a permission dialog appears, **stop and ask the owner**; default to Allow once only.
- Criterion 1's `hot` counts only the owner's interactive sessions; rig/agent-produced observations don't count.
  **This currently rests on the single discipline of "always carry the scratch env on every call"**: `AGENT_OS_ROOT` is already exported into `~/.zshrc`, so the one time you forget `AOS_STORE_DIR` it writes straight into the production DB, and after it's written **no field can tell who drove it** (defect AR: the host's `OPENCODE_CLIENT` has only one assignment, `"acp"`, and the TUI doesn't write it ⇒ human and agent are both `cli`).
  ⇒ don't write a source field to patch this hole (that would be fake), and don't describe `doctor`'s `hot` directly as "how many times the owner used it"; always report the reading as two numbers, "upper bound N / provable lower bound M", see `docs/experiment/stage-1-usage-ledger.md §4bis`.
- Prompts are fully synthetic; session bodies never enter the repo or the docs; plugin logs show only key names/indices/counts, never values.
- If you need to change `~/.config/opencode/**` or need a hook the host lacks ⇒ stop and report; that is the owner's decision.

## Release / version numbers

- The authoritative version number is `pyproject.toml`'s `[project] version` (currently `0.1.0`).
- The engine has another hard-coded copy that must equal it: `aos/__init__.py`'s `__version__`; bump both together, missing one is drift.
- **When to bump**: a change that alters externally visible behavior (command, contract, recall, or gating semantics) is bumped in the same commit; pure docs, pure tests, pure internal refactors are not bumped.

## Commits and docs

- Commit messages are **English** and always use Conventional Commits + scope (e.g. `chore(docs):`, `fix(recall):`, `feat(memory):`), with the scope being the affected module or surface.
- **Docs and config/tests are committed separately**: doc changes (`*.md`, `docs/`) must not be bundled into the same commit as config/test changes — this is "one change = one commit" applied at commit granularity.

## Delivery cadence

One change = one commit; the report has five fixed items: which files changed, test results (before/after counts + new case names), behavior change before→after (including the part **deliberately left unchanged**), risk and rollback (can it be reverted as a single commit), whether an existing contract was broken.
When a step is skipped, you must be able to prove that step is still executable.
