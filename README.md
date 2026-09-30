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
│   ├── contract/               # frozen preflight/postflight contract (schema 1.1)
│   ├── core/
│   │   ├── routing/            # hybrid router + taxonomy resolution
│   │   │   └── registry/       # engine vocab, role catalog, taxonomy map
│   │   ├── memory/             # SQLite store, retrieve, record, evolve, policy,
│   │   │                       #   conflict, evaluate, inject (the block renderer),
│   │   │                       #   authoring (add/seed)
│   │   ├── loop/               # state machine + lifecycle + stages + team
│   │   ├── orchestration/      # multi-agent team formation + collaboration
│   │   ├── validation/         # project build detection + code validation
│   │   └── evidence/           # collection, recovery planning, provenance
│   ├── adapters/               # Provider protocol: opencode / host_delegate / test_provider
│   └── cli/main.py             # run | doctor | preflight | postflight | review | route | memory
├── content/                    # overridable JSON layer (see content/README.md)
│   └── memory/seed/            # cold-start memories (loaded by `aos memory seed`)
├── store/                      # runtime state (gitignored; see store/.gitignore)
│   ├── aos.db                  # SQLite memory store
│   └── loops/  evidence/  pending-postflight/
└── tests/                      # conftest + per-module tests
```

The **repository is the runtime root**. Nothing points at `~/.agents`; every
path resolves from `AGENT_OS_ROOT` (defaulting to the repo itself).

## Quick start

```bash
./bin/aos doctor                       # show resolved paths and health
./bin/aos memory seed                  # cold start: load content/memory/seed into the store
./bin/aos memory list                  # what the engine knows
./bin/aos memory inspect <id>          # a memory and why it believes it
./bin/aos route "fix the null pointer crash"
./bin/aos run "add a /health endpoint" --cwd /path/to/project --provider test_provider
./bin/aos review list                  # pending memory promotions
```

A fresh store holds nothing, and with nothing stored recall is empty, so no
candidate is ever proposed and no learning is observable at all. `memory seed`
is therefore step one, not a nicety.

`run` executes the full lifecycle (preflight → execute → postflight) against a
real provider and prints the postflight contract. Use `--provider test_provider`
for a deterministic dry run, `--expect <substr>` to assert on output, and
`--no-validate` to skip the post-execution build/test validation.

### Host integration entry points

Hosts do not call the Python API directly — they speak the JSON contract over
stdin/stdout:

```bash
echo '{"schema_version":"1.1","phase":"preflight","task":"...","session_id":"...","cwd":"..."}' \
  | ./bin/aos preflight --payload-stdin
```

The response's `memory.injection.text` is the block to append to the host's
system prompt; an empty string means push nothing.

## The frozen contract (`schema_version = "1.1"`, serves `1.0`)

The preflight/postflight JSON shapes are the public interface. They live in
`aos/contract/` and are locked by `tests/test_contract.py`, which holds the 1.0
field set as a literal and asserts the emitted document equals that set plus
only the declared additions — so a key cannot be dropped, and one cannot be
added quietly either.

A request may declare `1.0` or `1.1` and the response is echoed in the version
it declared. A declaration the engine does not speak is **rejected** at the CLI
(exit `3`, a fallback document) rather than quietly answered in the engine's own
version — replying 1.1 to a host that believes it negotiated 1.2 is a worse trap
than saying no. 1.1 is additions only, which is what lets a host still pinned to
1.0 keep passing its own check while reading nothing new.

**Request payload** — `preflight` requires `task`:

```json
{ "schema_version": "1.0|1.1", "phase": "preflight",
  "task": "(required)", "task_id": "", "session_id": "", "cwd": "",
  "memory_mode": "enabled|disabled|fallback",
  "provider": "opencode|host_delegate|test_provider", "model": "" }
```

**`postflight` request** requires `task_id` and `loop_id`, and is where the host
reports what actually happened — this is the learning signal, and it is dropped
at the CLI boundary at the engine's peril:

```json
{ "schema_version": "1.1", "phase": "postflight",
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
| skills dir | `AOS_SKILLS_DIR` | `<content>/skills` |
| knowledge dir | `AOS_KNOWLEDGE_DIR` | `<content>/knowledge` |

Two more the engine reads directly: `AOS_SESSION_ID` (names the evidence
directory; generated when unset) and `AOS_REGISTRY_PATH` (override the routing
registry). `tests/test_config.py`
guards against any hardcoded absolute path creeping back into `aos/`.

## Memory and the learning gate

SQLite is the single source of truth. Tables: `memories`, `memory_tags`,
`memory_roles`, `observations`, `candidates`, `learning_reviews`,
`retrieval_log`, `telemetry_events`.

Retrieval is deterministic: tag / domain / role / keyword overlap, plus a type
bonus and a quality multiplier, with the decay factor actually applied and the
query written to `retrieval_log`.

Learning (`aos/core/memory/evolve.py`) runs observation → candidate → resolve →
validate → **gate** → promote. Thresholds come from `content/policies/*.json`
(built-in defaults when absent). **Any hypothesis or low-evidence candidate is
held as a `learning_reviews(status='pending')` row and is never auto-promoted.**
A human resolves it:

```bash
./bin/aos review list
./bin/aos review approve <review-id>
./bin/aos review reject  <review-id>
```

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

## Multi-agent orchestration

`aos/core/orchestration/` decides whether a task needs a team (≥2 domains, or
`hard` difficulty) and, if so, forms one from the engine role catalog using
data-driven rules in `rules.json`. Collaboration is split into
`task_decomposer` / `scheduler` / `aggregator` / `trace`. Roles carry `domain`
and `dependencies`, so the team plan resolves execution order.

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
OpenCode plugin is the adapter that speaks it; it is designed but not yet
written, and nothing here installs into `~/.config/opencode/`. Until the plugin
lands, `./bin/aos` is the entry point.

The previous `hosts/opencode/` tree is deleted. It pointed at a retired
`~/.agents` layout that no longer exists, neither `aos/` nor `tests/` imported
it, and the engine never read a byte of it — so a fresh clone could not start
it, and reading it was worse than useless.

## The content layer

`content/` holds what a host may edit without touching the engine:

| Path | Status |
|---|---|
| `content/memory/seed/` | **live** — loaded by `aos memory seed`; the cold start |
| `content/policies/` | empty; `policy.load_policy` falls back to built-in defaults |
| `content/skills/`, `content/knowledge/` | not created — declared paths only |

`content/policies/*.json` overrides `aos/core/memory/policy.py`'s defaults, so
thresholds can be retuned per deployment without a code change. Routing rules,
the role catalog and the taxonomy map are resolved from
`aos/core/routing/registry/` first, and `AOS_REGISTRY_PATH` overrides that — the
engine works with an entirely empty `content/`, which is why every path here is
optional and none is validated.
