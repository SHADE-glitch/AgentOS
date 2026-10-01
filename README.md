# Agent OS

Agent OS is an external "brain" for coding agents (OpenCode, and later other
hosts). It wraps a host agent and adds four capabilities:

```text
Route    pick the right skill and role for the task
Recall   retrieve the memories that apply to it
Inject   render them into one block the host puts in front of the model
Learn    record the outcome and promote repeated lessons into memory
```

The host executes; the engine decides what it should know first and what the
episode taught afterwards. Actual code changes are never made here —
`auto_modify_code` is `False` everywhere.

The engine is pure Python standard library — **zero third-party dependencies**.
All configuration, rules, roles and policies are JSON.

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
│   └── cli/main.py             # run | doctor | preflight | postflight | review | route | memory
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
./bin/aos review reject  <review-id> [--as X] # --as turns a rejection into a weakening signal
./bin/aos review sync                         # settle candidates from any other writer
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
python -m pytest tests/ -q
```

pytest is the only runner: the suite is built on pytest fixtures, so
`python -m unittest discover -s tests` collects **zero** tests and exits `0` —
a green that means nothing. Do not wire it into anything as a check.

Each test runs against a hermetic `tmp_path` store (autouse `hermetic_env`
fixture), so tests are side-effect free and parallel-safe. The repository's own
`store/aos.db` is never touched by a test.

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

The previous `hosts/opencode/` tree is deleted. It pointed at a retired
`~/.agents` layout that no longer exists, neither `aos/` nor `tests/` imported
it, and the engine never read a byte of it — so a fresh clone could not start
it, and reading it was worse than useless.

## The content layer

`content/` holds what a host may edit without touching the engine:

| Path | Status |
|---|---|
| `content/memory/seed/` | **live** — loaded by `aos memory seed`; the cold start |
| `content/policies/` | **shipped** — six files, each key-for-key equal to the built-in defaults; edit any value to retune without touching code |

`content/policies/*.json` overrides `aos/core/memory/policy.py`'s defaults, so
thresholds can be retuned per deployment without a code change. Routing rules,
the role catalog and the taxonomy map are resolved from
`aos/core/routing/registry/` first, and `AOS_REGISTRY_PATH` overrides that — the
engine works with an entirely empty `content/`, which is why every path here is
optional and none is validated.
