# Agent OS

Agent OS is an external "brain" for coding agents (OpenCode, and later other
hosts). It wraps a host agent and adds four capabilities:

```text
Route    pick the right role for the task
Recall   retrieve the memories that apply to it
Inject   hand the routed prompt to the host to execute
Learn    record the outcome and promote repeated lessons into memory
```

The engine is pure Python standard library — **zero third-party dependencies**.
All configuration, rules, roles and policies are JSON.

## Repository layout

```text
AgentOS/
├── bin/aos                     # thin shim -> python3 -m aos.cli
├── pyproject.toml              # package metadata + pytest config (no runtime deps)
├── aos/                        # the engine (stdlib only)
│   ├── config.py               # resolve_root() + Paths (every path injectable)
│   ├── contract/               # frozen preflight/postflight contract (schema 1.0)
│   ├── core/
│   │   ├── routing/            # hybrid router + taxonomy resolution
│   │   │   └── registry/       # engine vocab, role catalog, taxonomy map
│   │   ├── memory/             # SQLite store, retrieve, record, evolve, policy,
│   │   │                       #   conflict, evaluate
│   │   ├── loop/               # state machine + lifecycle + stages + team
│   │   ├── orchestration/      # multi-agent team formation + collaboration
│   │   ├── validation/         # project build detection + code validation
│   │   └── evidence/           # collection, recovery planning, provenance
│   ├── adapters/               # Provider protocol: opencode / host_delegate / test_provider
│   └── cli/main.py             # run | doctor | preflight | postflight | review | route | memory
├── content/                    # deferred content layer (README + overridable JSON)
├── store/                      # runtime state (gitignored; see store/.gitignore)
│   ├── aos.db                  # SQLite memory store
│   └── loops/  evidence/  pending-postflight/
├── hosts/                      # host integrations (frozen this round — see below)
└── tests/                      # conftest + per-module tests
```

The **repository is the runtime root**. Nothing points at `~/.agents`; every
path resolves from `AGENT_OS_ROOT` (defaulting to the repo itself).

## Quick start

```bash
./bin/aos doctor                       # show resolved paths and health
./bin/aos route "fix the null pointer crash"
./bin/aos run "add a /health endpoint" --cwd /path/to/project --provider test_provider
./bin/aos memory list
./bin/aos review list                  # pending memory promotions
```

`run` executes the full lifecycle (preflight → execute → postflight) against a
real provider and prints the postflight contract. Use `--provider test_provider`
for a deterministic dry run, `--expect <substr>` to assert on output, and
`--no-validate` to skip the post-execution build/test validation.

### Host integration entry points

Hosts do not call the Python API directly — they speak the JSON contract over
stdin/stdout:

```bash
echo '{"schema_version":"1.0","phase":"preflight","task":"...","session_id":"...","cwd":"..."}' \
  | ./bin/aos preflight --payload-stdin
```

## The frozen contract (`schema_version = "1.0"`)

The preflight/postflight JSON shapes are the public interface. They live in
`aos/contract/` and are locked by `tests/test_contract.py`, which asserts the
exact field set the host plugins read — so the contract cannot silently break a
host.

**Request payload** (both phases share it; fields optional unless noted):

```json
{ "schema_version": "1.0", "phase": "preflight|postflight",
  "task": "(preflight, required)", "task_id": "(postflight, required)",
  "loop_id": "(postflight, required)", "session_id": "", "cwd": "",
  "memory_mode": "enabled|disabled|fallback",
  "provider": "opencode|host_delegate|test_provider", "model": "" }
```

**preflight response** carries `aos_status`, the generated `task_id` / `loop_id`
/ `session_id`, `classification`, `router` (`lead_skill` abstract,
`lead_role` concrete, confidence, escalation reason, artifact), `memory`
(retrieved memories + hypotheses), `skill`, `warnings` and `artifacts`.

**postflight response** carries `final_status`, `evidence_path` + `evidence`,
`recovery`, `learning` (candidates / pending reviews / promoted) and `replayed`.

`aos_status` is one of `ok | degraded | fallback`; `final_status` one of
`completed | partial | failed`. Validation lives in
`aos/contract/{preflight,postflight}.py`; the legacy nested shape is rendered on
demand by `aos/contract/legacy.py`.

## Configuration

| Field | Environment variable | Default |
|---|---|---|
| root | `AGENT_OS_ROOT` | repository root |
| store dir | `AOS_STORE_DIR` | `<root>/store` |
| database | `AOS_DB_PATH` | `<store>/aos.db` |
| content dir | `AOS_CONTENT_DIR` | `<root>/content` |
| skills dir | `AOS_SKILLS_DIR` | `<content>/skills` |
| policies dir | `AOS_POLICIES_DIR` | `<content>/policies` |

Other recognised variables: `AOS_RUNTIME_PROVIDER`, `AOS_RUNTIME_MODEL`,
`AOS_SESSION_ID`, `AOS_HOST_PLUGIN_ACTIVE`, `AOS_MIN_MEMORY_SCORE`. The legacy
`AGENT_OS_HOME` is accepted with a one-time warning. `tests/test_config.py`
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
python -m pytest tests/ -q                    # dev dependency: pytest
python -m unittest discover -s tests          # stdlib fallback
```

Each test runs against a hermetic `tmp_path` store (autouse `hermetic_env`
fixture), so tests are side-effect free and parallel-safe.

## Hosts (frozen this round)

`hosts/opencode/` and `hosts/freebuff/` are **intentionally disconnected** in
this round. Their plugin entry points still reference the retired
`runtime/hosts/...` paths and `~/.agents`, which no longer exist. Host
integration is the next round's work: point the plugins at `bin/aos` (the JSON
contract above) and at the new `store/` paths. Until then, `./bin/aos` is the
supported entry point.

## Deferred: the content layer

`content/` (skills, knowledge, policies) is deferred. The engine ships built-in
defaults — role catalog, taxonomy map, orchestration rules — so routing,
orchestration and the loop work with an empty content layer. The content layer
is meant to be rebuilt on top of the interfaces defined here, overriding the
engine defaults via the `AOS_*_DIR` variables.
