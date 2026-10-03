# Agent OS

Agent OS is an **external evidence and governance layer** for a coding agent that
already exists. Today that host is [OpenCode](https://opencode.ai), reached through
one plugin and one JSON contract; the engine itself never calls the host and never
runs code.

The loop it closes:

```text
run      the host does the work
record   what happened is filed as an observation
judge     a verdict is synthesised; weak or contested ones go to a HUMAN
promote   the human's approval writes the memory
recall    the next similar task gets that memory injected
```

Nothing here is a "second brain" in the marketing sense: it is a ledger with a human
gate in the middle, and the whole point is that **the gate is what makes the ledger
trustworthy**. `auto_modify_code` is `False` everywhere; the engine proposes, a person
decides.

The engine is pure Python standard library — **zero third-party dependencies, no MCP,
no network calls**. Rules, thresholds, roles and taxonomy are JSON under `content/`.

## Status — read this before you build on it

This repository is honest about which half of itself is proven. The claims below are
labelled with the four grades used throughout the docs
(`Verified` measured on a real host / `Inferred` behaviour derived from executed code /
`Unconfirmed` designed but not yet measured / `Judgment` a decision, not a fact).

**Proven (`Verified`, with the measurement named in `docs/architecture/agent-os-v2.md` §15):**

- The loop runs end to end on a real host: preflight → injection → postflight → gate → promotion.
- The injected block **reaches the model**: an inert control arm in the same cwd, same prompt,
  counted **583 fewer input tokens**, and only the armed arm stated a rule that existed in no other source.
- **A human approval changes what the next run recalls**: on the real store, injection went
  1122 chars / 3 memories → 1359 chars / 4 memories, and `+237` was predicted from a copy of the
  store *before* the run, not read off afterwards.
- Method-level experience survives collection: "tried A, A failed, switched to B, B worked"
  crosses the host seam as an ordered, redacted fingerprint, dedupes to **one** memory per decision,
  and renders in the injected block as a procedure — while buying **0.00 verdict weight** (pinned by test).
- Fail-open by construction: an absent store, an absent neighbour database, or a slow engine degrades
  the injection and says so in `warnings`; it never blocks a prompt.
- Disabling the integration is byte-identical to not installing it (JS assertion, `tests/js/plugin.test.mjs`).

**Not proven — and this is the reason the project may still be cancelled:**

- **Does injected experience make the answer better?** Never measured. The only evidence
  is that the *shape* changed (the armed arm produced the requested scaffolding; the inert arm
  produced none of it) on a prompt the model could already answer. Whether it turns a
  wrong answer right, on tasks the model cannot answer without project context, is open.
- **Does it reduce future attempts or change the first action?** Unmeasured.
- **Is it worth more than the plain `AGENTS.md` / memory features the host already has?**
  No blind comparison exists.
- **Is the thing being measured human usage?** Undecidable today: the host exposes no
  "who drove this run" field, so `doctor`'s `hot` count is an **upper bound** with a
  provable-by-human lower bound of 0 (defect `AR`).
- Persistence of a lesson across turns is weak: in a 14-round live sequence, lessons
  did not reliably stick to the second round.

**Standing decision (criterion 1, `docs/decision/positioning.md` §6):** if fewer than 30
real `source='hot'` runs exist four weeks after being wired up, feature work stops and the
repo shrinks to the three parts that can survive on their own. Read the current number with
`./bin/aos doctor --json` — do not trust any figure written in a document.

## Start here (a new developer)

```bash
git clone https://github.com/SHADE-glitch/AgentOS && cd AgentOS
python3 -m pytest                      # 496 passed — the suite IS the specification
node --test tests/js/plugin.test.mjs   # 29 pass — the host seam
./bin/aos doctor --json                # what this checkout has actually done
./bin/aos memory seed                  # a fresh store recalls nothing until this runs
./bin/aos review list                  # the human gate, and what approving each row would do
```

Then read, in this order: `AGENTS.md` (the checks that are not negotiable),
`docs/architecture/agent-os-v2.md` §12 (defect register) and §15 (how far the evidence goes),
`docs/plan/final-plan.md` §11 (the execution log — mostly a record of mistakes and how each was caught).


## Repository layout

```text
AgentOS/
├── bin/aos                     # thin shim -> python3 -m aos.cli
├── pyproject.toml              # package metadata + pytest config (no runtime deps)
├── aos/                        # the engine (stdlib only)
│   ├── config.py               # resolve_root() + Paths (every path injectable)
│   ├── contract/               # frozen preflight/postflight contract (schema 1.2)
│   ├── core/
│   │   ├── routing/            # hybrid router + taxonomy resolution
│   │   │   └── registry/       # engine vocab, role catalog, taxonomy map
│   │   ├── memory/             # SQLite store, retrieve, record, evolve, policy,
│   │   │                       #   conflict, evaluate, inject (the block renderer),
│   │   │                       #   authoring (add/seed)
│   │   ├── loop/               # state machine + lifecycle + stages
│   │   ├── validation/         # project build detection + code validation
│   │   └── evidence/           # collection, recovery planning, provenance
│   ├── adapters/               # Provider protocol: host_delegate / test_provider
│   └── cli/main.py             # doctor | preflight | postflight | route | run | pending | backfill | memory | review
├── integrations/opencode/      # the plugin (loaded on this machine 2026-10-01) + its fixture tests
├── content/                    # overridable JSON layer (see content/README.md)
│   └── memory/seed/            # cold-start memories (loaded by `aos memory seed`)
├── store/                      # runtime state (gitignored; see store/.gitignore)
│   ├── aos.db                  # SQLite memory store
│   └── loops/  evidence/  pending-postflight/
└── tests/                      # conftest + per-module tests, plus tests/js/ (node --test)
```

The **repository is the runtime root**. Nothing points at `~/.agents`; every
path resolves from `AGENT_OS_ROOT` (defaulting to the repo itself).

## Quick start

```bash
./bin/aos doctor                       # paths, schema, and what the store has actually done
./bin/aos doctor --json                # the same facts as a document (a host negotiates on this)
./bin/aos memory seed                  # cold start: load content/memory/seed into the store
./bin/aos memory list                  # what the engine knows
./bin/aos memory inspect <id>          # a memory and why it believes it
./bin/aos memory refresh               # recompute derived state: expiry, fact keys, counts, decay
./bin/aos memory retire <id> --reason  # stop trusting one: out of recall, row and history kept
./bin/aos route "fix the null pointer crash"
./bin/aos run "add a /health endpoint" --cwd /path/to/project --provider test_provider
./bin/aos review list                  # what the gate is asking a person about
./bin/aos review sync                  # settle written candidates into the queue without another run
./bin/aos backfill plan                # what a read-only source db would yield, writing nothing
AOS_BACKFILL_DB=... ./bin/aos backfill run --apply   # off unless you name the source
```

A fresh store holds nothing, and with nothing stored recall is empty, so no
candidate is ever proposed and no learning is observable at all. `memory seed`
is therefore step one, not a nicety.

`run` executes the full lifecycle (preflight → execute → postflight) against a
real provider and prints the postflight contract. Use `--provider test_provider`
for a deterministic dry run, `--expect <substr>` to assert on output, and
`--no-validate` to skip the post-execution build/test validation.

`backfill` is the only code in the repository that looks at another tool's
database, and it does nothing at all unless `AOS_BACKFILL_DB` names one. The
source is opened `mode=ro` (never `immutable=1` — a live WAL exists), only
structural columns and JSON paths are whitelisted, and nothing a person typed
is ever copied: session titles, part text, tool input/output/error bodies and
todo contents are outside the whitelist, not "skipped for now". What lands is
counts and enums, tagged `source='backfill'` with `outcome='partial'` — read
history, not a verdict. It does not enter the human review queue and it does not
change recall; `doctor --json` counts `hot` and `backfill` separately so a
backfill can never be mistaken for evidence that the loop is live.

### Host integration entry points

Hosts do not call the Python API directly — they speak the JSON contract over
stdin/stdout:

```bash
echo '{"schema_version":"1.2","phase":"preflight","task":"...","session_id":"...","cwd":"..."}' \
  | ./bin/aos preflight --payload-stdin
```

The response's `memory.injection.text` is the block to append to the host's
system prompt; an empty string means push nothing.

## The frozen contract (`schema_version = "1.2"`, serves `1.0` and `1.1`)

The preflight/postflight JSON shapes are the public interface. They live in
`aos/contract/` and are locked by `tests/test_contract.py`, which holds the 1.0
field set as a literal and asserts the emitted document equals that set plus
only the declared additions — so a key cannot be dropped, and one cannot be
added quietly either.

A request may declare `1.0`, `1.1` or `1.2` and the response is echoed in the
version it declared. A declaration the engine does not speak is **rejected** at
the CLI (exit `3`, a fallback document) rather than quietly answered in the
engine's own version — replying 1.2 to a host that believes it negotiated 1.1 is
a worse trap than saying no. 1.1 was additions only. **1.2 removes one nested
key, `skill.skills_loaded`, which no producer ever filled** (the only value a
host could read was `[]`), so behaviour is unchanged while the shape is not; the
removal is pinned by a test so it cannot come back as decoration.

**Request payload** — `preflight` requires `task`:

```json
{ "schema_version": "1.0|1.1|1.2", "phase": "preflight",
  "task": "(required)", "task_id": "", "session_id": "", "cwd": "",
  "memory_mode": "enabled|disabled|fallback",
  "provider": "host_delegate|test_provider", "model": "" }
```

**`postflight` request** requires `task_id` and `loop_id`, and is where the host
reports what actually happened — this is the learning signal, and it is dropped
at the CLI boundary at the engine's peril:

```json
{ "schema_version": "1.2", "phase": "postflight",
  "task_id": "(required)", "loop_id": "(required)", "session_id": "", "cwd": "",
  "outcome": "success|failure|partial", "quality_score": 4.5,
  "test_command": "", "test_stdout": "", "test_stderr": "", "test_exit_code": 0,
  "compile_command": "", "expected_files": ["src/app.py"], "validate": true }
```

`outcome` is optional but consequential: with no outcome reported the loop is
recorded `partial`, never `success`. Any field the engine does not read comes
back named in `warnings` instead of being ignored in silence.

**preflight response** carries `aos_status`, the generated `task_id` / `loop_id`
/ `session_id`, `classification`, `router` (`lead_skill` abstract,
`lead_role` concrete, confidence, escalation reason, artifact), `memory`
(retrieved memories + hypotheses, `status` = recall health
`ok|degraded|skipped|fallback`, and 1.1's `injection` — the ready-to-append
`<agent_os>` block with its `structured` fields, `char_count`, `truncated`,
`memory_ids` and `dropped`), `skill`, `warnings` and `artifacts`.

**postflight response** carries `final_status`, `evidence_path` + `evidence`,
`recovery`, `learning` (candidates / pending reviews / promoted), `replayed` and
1.1's `aos_error` (why a fail-open document was returned) + `warnings`.

`aos_status` is one of `ok | degraded | fallback`; `final_status` one of
`completed | partial | failed`. A document the engine could not produce reports
`failed`, never `completed`. Validation lives in
`aos/contract/{preflight,postflight}.py`.

## Configuration

| Field | Environment variable | Default |
|---|---|---|
| root | `AGENT_OS_ROOT` | repository root |
| store dir | `AOS_STORE_DIR` | `<root>/store` |
| database | `AOS_DB_PATH` | `<store>/aos.db` |
| content dir | `AOS_CONTENT_DIR` | `<root>/content` |
| memory dir | `AOS_MEMORY_DIR` | `<content>/memory` |
| policies dir | `AOS_POLICIES_DIR` | `<content>/policies` |
| basic-memory index (read-only) | `AOS_BM_DB` | `~/.basic-memory/memory.db` |
| basic-memory config dir (locates its vault, read-only) | `AOS_BM_CONFIG_DIR` | `~/.basic-memory` |
| publish command prefix (argv, not a path) | `AOS_BM_BIN` | `uvx basic-memory` |

`AOS_BM_BIN=""` is the off-switch for publishing an approved lesson into
basic-memory; the other one is `"enabled": false` in
`content/policies/external_write.json`. Neither changes what the gate decides:
`store/` is written first and stays the only thing recall reads.

Two more the engine reads directly: `AOS_SESSION_ID` (names the evidence
directory; generated when unset) and `AOS_REGISTRY_PATH` (override the routing
registry). `tests/test_config.py`
guards against any hardcoded absolute path creeping back into `aos/`.

## Memory and the learning gate

SQLite is the single source of truth. Tables: `memories`, `memory_tags`,
`memory_roles`, `observations`, `candidates`, `learning_reviews`,
`retrieval_log`, `telemetry_events`, `backfill_state`. The schema is versioned by
`PRAGMA user_version` (currently v5); `aos/core/memory/schema.sql` is the frozen
v1 baseline and every change after it is a named, append-only migration
(`aos memory migrate [--dry-run]`).

A memory has four separate axes, and collapsing any two of them is how a store
becomes noise:

| Axis | Values | Decides |
|---|---|---|
| `type` | `episodic` `semantic` `procedural` `failure` `preference` `constraint` | how it is **worded** in the injected block |
| `evidence_level` | `hypothesis` → `benchmark_evaluated` → `runtime_validated` → `independent_validated` → `real_project_validated` → `production_validated` | how far it has been **checked** |
| `status` | `candidate` `active` `verified` `deprecated` `superseded` `invalidated` `archived` | where it is in its **life** |
| `scope` | `global` `project:<id>` `session:<id>` | where it may be **recalled at all** |

`lane` carries `hypothesis` separately from `type`, because "unproven" is an
evidence state and not a kind of memory — under v1 it was written three ways
(a type, an evidence level, and an `H-` id prefix) and the three could disagree.

Nothing becomes `verified` by being observed once. An authored memory is born
`status=candidate, lane=hypothesis, evidence_level=hypothesis` unless it declares
`--verified`, and only the promotion path or a human gate moves it out of that.

Retrieval is deterministic: tag / domain / role / keyword overlap, plus a type
bonus and a quality multiplier, with the decay factor actually applied and the
query written to `retrieval_log`.

Learning (`aos/core/memory/evolve.py`) runs observation → candidate → resolve →
validate → **gate** → promote. Thresholds come from `content/policies/*.json`
(built-in defaults when absent). **Any hypothesis or low-evidence candidate is
held as a `learning_reviews(status='pending')` row and is never auto-promoted.**
A human resolves it:

A verdict and an attribution are two different claims. `review label <id> --outcome
failure` records what the human judged and stops there — nothing is credited or blamed,
and the CLI says so in terms of what to type next. `--skill <name>` is the second claim
("this kind of work is what the run proves"), and only memories whose category or tags
are about that skill are implicated by it. Being recalled is not being the cause: the
engine's own record path has required that since P2, while a labelled run bypassed it.

```bash
./bin/aos review list                        # each row says what approving would do
./bin/aos review label <id...> --outcome X [--skill S]   # answer the queue; the consequence prints back
./bin/aos review approve <review-id>         # promotion, or a conflict's supersede
./bin/aos review approve <id> --title T --body B --when W --tags A,B
                                             # create only: the reviewer writes the 因为 no signal has,
                                             # and names the subject --tags is what makes the lesson
                                             # findable again — the router's own tags are not a subject
./bin/aos review reject  <review-id> [--as X] # --as turns a rejection into a weakening signal
./bin/aos review sync                         # settle candidates from any other writer
./bin/aos memory retire <id> --reason R       # stop trusting one; the row and its history stay
```

Thresholds live in `content/policies/*.json` and are read per resolved path, so
retuning one is an edit, not a code change: `min_auto_confidence` decides when a
run must be handed to a person, `recall_statuses` decides which memories a host may
be shown, `revalidate_after` expiry is stepped by `aos memory refresh`.

## Loop lifecycle

One explicit state machine, shared by the CLI and by hosts (so a host-driven
postflight also closes the learning loop):

```text
route -> resolve_role -> recall -> plan -> execute
      -> evidence -> validate -> record -> evolve -> finalize
```

`preflight()` runs the front half and persists a `LoopState` as atomic JSON under
`store/loops/`; `postflight()` runs the back half with an idempotency guard
(replayed runs are flagged). `run()` is both halves plus execution.

## What the engine deliberately does not do

No multi-agent orchestration (removed: the routed decision never carried more
than one domain, so the team path was structurally unreachable and its output
had no consumer), no provider that drives opencode (`opencode run` is the host's
job, not the brain's), no second skill system, no telemetry writer.
See `docs/decision/positioning.md` and `docs/architecture/agent-os-v2.md` §11.

## Validation and evidence

Before execution, `project_preflight` detects the build system, language
version, declared services and validation commands. After execution,
`code_validator` inspects the git diff and runs the detected compile/test
commands against a caller-supplied baseline (each command runs exactly once).
A pluggable `bug_scanner` hook replaces the old hardcoded Java check. Recovery
is **plan-only** — `auto_modify_code` is `False` everywhere; the engine never
rewrites code on its own.

Evidence is collected into `store/evidence/<session>/`, with a worktree-aware
`git_root` (handles linked worktrees where `.git` is a file) and per-symbol
provenance.

## Tests

```bash
python3 -m pytest                              # 496 passed
node --test tests/js/plugin.test.mjs           # 29 pass / 0 fail
```

Two traps that cost this project real time, so they are written next to the commands:

- **Do not append `-q` to pytest.** `pyproject.toml` already sets `addopts = "-q"`; a second `-q`
  suppresses the summary line entirely, so `pytest -q | grep passed` prints nothing and a counting
  script silently reads zero. Use `--collect-only -q` if you need per-file counts.
- **Do not run `node --test tests/js/`.** The directory form executes `tests/js/fake-aos.cjs` as a
  test file and reports `# tests 1 / # fail 1` — a red that means nothing. Name the file.

pytest is the only runner: the suite is built on pytest fixtures, so
`python -m unittest discover -s tests` collects **zero** tests and exits `0` —
a green that means nothing. Do not wire it into anything as a check.

Each test runs against a hermetic `tmp_path` store (autouse `hermetic_env`
fixture), so tests are side-effect free and parallel-safe. The repository's own
`store/aos.db` is never touched by a test. The same fixture points `AOS_BM_DB`,
`AOS_BM_CONFIG_DIR` and `AOS_BM_BIN` at paths that do not exist, so no test can
read — or publish into — a real neighbour notebook.

There is also a small test suite for the live-run rig:
`python3 -m pytest --collect-only -q integrations/opencode/live/tests` (15 cases).

## Host integration

A host reaches the engine only through `./bin/aos` and the JSON contract above —
there is no second host protocol and no Python API for hosts to import. The
OpenCode plugin that speaks it exists at
`integrations/opencode/plugin/agent-os.js` (three hooks: `chat.message` →
preflight, `experimental.chat.system.transform` → append one element,
`event`/`session.idle` → postflight, resolving a session back to a loop through
`aos pending` rather than by reading the store's files). **This repository never
installs it** — nothing in it writes to `~/.config/opencode/` on its own. It was
loaded on the owner's machine on 2026-10-01 by hand, as exactly two reversible
artifacts (a symlink in `plugin/` and one env prefix on the `opencode` alias); see
`integrations/opencode/README.md` for those artifacts, for the fixture proof of
disable-clean / additive-only / reuse-not-rebuild, and for what remains
`[Unconfirmed]` until a real session runs.

What the seam has been measured to do lives in `docs/architecture/agent-os-v2.md` §15: the block
demonstrably reaches the model (**+583** input tokens against an inert control arm in the same cwd),
and the gate demonstrably changes what the next run recalls — but **nothing has ever measured whether
injected experience improves an answer**, which is the open half of "is this worth keeping". The
test-and-fix loop is therefore closed in favour of observation: `./bin/aos doctor`'s `hot` and `recall`
lines decide it, against criterion 1, by 2026-10-29.

The previous `hosts/opencode/` tree is deleted. It pointed at a retired
`~/.agents` layout that no longer exists, neither `aos/` nor `tests/` imported
it, and the engine never read a byte of it — so a fresh clone could not start
it, and reading it was worse than useless.

## The content layer

`content/` holds what a host may edit without touching the engine:

| Path | Status |
|---|---|
| `content/memory/seed/` | **live** — loaded by `aos memory seed`; the cold start |
| `content/policies/` | **shipped** — eight files (`decay` `external` `external_write` `injection` `outcome` `promotion` `rejection` `retrieval`), each key-for-key equal to the built-in defaults; edit any value to retune without touching code. Adding a ninth requires a matching section in `policy.DEFAULT_POLICIES` or `tests/test_config.py` fails — the reverse (a default with no file) is silent |

`content/policies/*.json` overrides `aos/core/memory/policy.py`'s defaults, so
thresholds can be retuned per deployment without a code change. Routing rules,
the role catalog and the taxonomy map are resolved from
`aos/core/routing/registry/` first, and `AOS_REGISTRY_PATH` overrides that — the
engine works with an entirely empty `content/`, which is why every path here is
optional and none is validated.

## Working on this repository

`AGENTS.md` holds the checks that are not negotiable for anybody editing it: which commands count as
green (and the one that reports a false red), how to probe the real store without writing to it, when
a fix must ship in two halves, and what may not be asserted without being measured. It is deliberately
thin — every line in it is something that was actually run, and the evidence lives in the documents it
points to rather than being restated there.

**Delivery rule:** one change = one commit, and a report with exactly five items — files touched;
test counts before and after plus the names of new cases; behaviour before→after **including what was
deliberately left unchanged**; risk and rollback (must be revertable as a single commit); whether the
contract broke. If you skipped a step, prove the step is still executable.

**Before you add anything.** Five failure modes account for most of this project's defect register
(`docs/architecture/agent-os-v2.md` §12, letters A–AS). Each has a guard, and each guard is the reason
a "small addition" is usually the bug:

| Shape | Real instance | Guard |
|---|---|---|
| declared, nobody writes it | `skills_loaded` was validated while always `[]`; `dedupe_key` had no generator | contract frozen-key tests; `test_reachability` |
| written, nobody reads it | `retrieval_log` rows existed before anything queried them | `test_reachability` |
| read, never assigned | `user_interrupted` (defect **AK**, still open): the plugin initialises it and no line sets it, so the contract's interruption veto never fires | named JS test (absent today — this is the honest gap) |
| display disagrees with execution | a `--dry-run` that printed what it would do, then did it anyway | `--dry-run` tests on `migrate` |
| proven only in a fixture | the DCP prompt collision was first proven against a replay of DCP's own line rather than the live stack | §15 grades each claim `[Verified]`/`[Unconfirmed]` explicitly |

**Places where the work is open, with the reason it is still open:**

- `AR` — the host exposes no "who drove this run". `OPENCODE_CLIENT` is only ever assigned `"acp"` and the
  TUI never writes it, so a human at the keyboard and an agent driving the TUI both read `cli`. Any
  `source` field added today would be a fabrication; the fix needs a contract change and is the owner's call.
- `AI` — a shell exit code is visible in `tool.execute.after`, but mapping it to `build_exit_code` /
  `test_exit_code` requires deciding "is this command a build or a test", and the plugin must not guess
  (that is self-grading, defect F3). No attribution rule has been approved.
- `AS` — pending-postflight crash records are keyed **per session** (`aos/core/loop/pending.py:39`) and
  only cleared by a postflight (`lifecycle.py:406`): 66 unreported loops left one file. So
  `doctor.pending_postflight.outstanding` is a lower bound, and `store/` has no delete path by design.
- Vestigial usage columns: `use_count`, `success_count`, `last_used_at` are read by the CLI and by
  `retrieve`'s ranking reasons but **no code path in `aos/` ever increments them** (verified by grep,
  2026-10-03). Real usage is computed at read time by `MemoryStore.usage_stats()`. `retrieve.py:449`
  therefore has a branch that cannot fire. Either wire the columns or delete them; leaving them is how
  the next reader trusts a zero.
- `revalidate_after` has exactly one writer — the author's `--revalidate-after` flag
  (`authoring.py:165`) — while `expire_due` (`store.py:494`) acts on it. Promotion renews
  `last_verified_at` but never the deadline, so a re-verified memory can still expire on a date
  written when it was created. Not yet judged as a defect.
- The seam where a published note can be mis-read again: recall skips notes whose stored frontmatter
  carries `agent_os: true` (`external.py:_owned_by_agent_os`), and the test pins only the boolean,
  the string `"false"`, and the absent marker. Two paths are unfixed and untested: a note whose
  `entity_metadata` fails to parse is read as `{}` and treated as a human note, and a human who deletes
  the marker re-creates the "one lesson, two contradictory labels" shape. Both need a decision
  (treat unparseable as ours? treat a lost marker as a claim of ownership?) rather than a patch.
- **Phase 2** (make basic-memory the home of memory *text*) is designed, not started. The measurements
  that constrain it are recorded in §16 and in `docs/plan/final-plan.md` §11: one `write-note` spawn is
  8.1–9.2 s against a 1200 ms preflight budget, `retrieve()` costs ~1 ms, and **basic-memory's index
  lags its markdown files** (an edit made directly to a `.md` leaves the indexed checksum and body
  unchanged until a bm process re-indexes) — so "text from bm" must say whether it reads the files or a
  stale index. Read-only note: loading every note file in a 52-note vault costs ~0.87 ms, less than
  reading bm's own index (~1.7–1.9 ms).

## Privacy and placeholders

This repository is public and was scrubbed before publication. Its documents describe real runs on the
owner's machine, so machine-specific identifiers were replaced with placeholders rather than deleted —
the numbers and the causality survive, the address book does not:

| Placeholder | Means |
|---|---|
| `<repo>` | the checkout of this repository |
| `<subject-project>` | the project a live run was performed against |
| `<rig>` / `<rig>-void` | scratch directories holding experiment scaffolding and sealed, voided attempts |
| `<bm-vault>` | the basic-memory note folder the read-only recall points at |
| `<local-trash>` | the desktop trash, cited when an experiment's subject project turned out to be deleted |
| `ses_redactedNN` | an anonymised host conversation id; distinct ids stay distinct |

Rules for anybody continuing this work, all of them enforced or checkable:

- No session text, prompt bodies, tool output or note contents in commits. Live experiments use
  synthetic prompts; the plugin log prints key names, indices and counts, never values.
- Real stores are read-only. Any run or experiment points `AOS_STORE_DIR` / `AOS_DB_PATH` / `AOS_BM_DB` /
  `AOS_BM_CONFIG_DIR` at scratch first. To exercise the neighbour CLI for real you must set
  **`BASIC_MEMORY_CONFIG_DIR` as well**, because that is what redirects basic-memory's own database —
  pointing only at a scratch config file still writes the owner's live index.
- `store/`, `*.db`, evidence bundles and pending records are gitignored; verify before a public push with
  `git ls-files | grep -E '^store/|\.db$'` (only `store/.gitignore` should appear).
- Nothing in this repository writes `~/.config/opencode/**`; installing the plugin is two manual,
  reversible artifacts described in `integrations/opencode/README.md`.
