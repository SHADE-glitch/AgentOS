# 🧠 Agent OS

> **An external evidence and governance layer for a coding agent.**
> Observations → a verdict → **a human gate** → promoted memory → recall that changes
> what the agent is told *next time*.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Third-party dependencies](https://img.shields.io/badge/third--party%20dependencies-0-green)
![Host contract](https://img.shields.io/badge/host%20contract-1.2-informational)
![SQLite schema](https://img.shields.io/badge/SQLite%20schema-v5-informational)
![Tests](https://img.shields.io/badge/pytest-502%20passed-brightgreen)
[简体中文 README](README.zh-CN.md)

The host (today [OpenCode](https://opencode.ai)) does the work. This engine decides what the
model should be told **before** it starts, and what the episode taught **after** it finished.
It never edits code: `auto_modify_code` is `False` on every path.

---

## 🧭 Why a human gate at all

Every project surveyed in [`docs/research/`](docs/research/) that auto-promotes what a model
said it learned ended up with memories that were confidently wrong. This one keeps a person in
the loop where the evidence is thin, and makes that the **only** way a lesson becomes durable:

```text
  ┌──────────── the host runs, the engine watches ────────────┐
  │                                                            │
  ▼                                                            │
📥 preflight ──▶ 🧭 route ──▶ 🔍 recall ──▶ 📝 inject ──▶ 🤖 host executes
                    ▲                                          │
                    │                                          ▼
                    ┌──────── 📚 promoted memory ◀── 🚪 HUMAN GATE ◀── 📊 verdict
                                    │
                                    └──▶ ✋ retire / decay (a demotion is permanent)
```

* **A verdict and an attribution are different claims.** Label a run `failure` and nothing is
  blamed; credit a memory with being recalled is how a store turns into noise.
* **Being recalled is not being the cause.** Candidates require explicit attribution.
* **Nothing is auto-promoted from a hypothesis.** It becomes a `pending` review row instead.

---

## 📊 Status — read this before you build on it

Claims are graded, the same way the docs grade them:
`✅ Verified` measured on a real host · `🟡 Inferred` · `⚠️ Unconfirmed` designed but unmeasured ·
`💭 Judgment` a decision, not a fact.

### ✅ What has been measured

| Claim | The measurement |
|---|---|
| The injected block reaches the model | Inert control arm, same cwd and prompt, counted **583** fewer input tokens |
| A human decision changes the next recall | On the real store: injection went **1122** chars / 3 memories → **1359** chars / 4, and `+237` was predicted from a copy *before* the run |
| Method-level experience survives collection | "tried A → A failed → switched to B → B worked" crosses the seam as an ordered redacted fingerprint, dedupes to one memory per decision — while buying **0.00** verdict weight (pinned by test) |
| It fails open | A missing store, a missing neighbour database or a slow engine degrades the injection and says why in `warnings`; a prompt is never blocked |
| Disabling it is free | With `AGENT_OS_ROOT` unset, `output.system` is byte-identical to having no plugin at all (JS assertion) |
| The engine never touches the host | No code path invokes `opencode`; hosts enter only via `bin/aos` + JSON |

### ⚠️ What has never been measured — the reason this project may still be cancelled

* ❓ **Does injected experience make answers better?** Never measured. What is proven is that the
  *shape* of the answer changed, on a question the model could already answer.
* ❓ Does it reduce future attempts, or change the **first** action? Open.
* ❓ Is it worth more than the host's own `AGENTS.md` / memory features? No blind comparison exists.
* ❓ **Were the counted runs driven by a human?** Undecidable today (defect `AR`): the host exposes
  no run-driver field, so `hot` is an upper bound whose provable-by-human lower bound is 0.
* ❓ Do lessons stick across turns? Weak evidence: in a 14-round live sequence, one round recalled 0.

> **⏳ Standing decision (criterion 1).** Fewer than **30** real `source='hot'` runs four weeks after
> wiring up ⇒ feature work stops and the repo shrinks to the three parts that survive alone.
> Window closes **2026-10-29**. Read the live number with `./bin/aos doctor --json` — never trust a
> figure copied out of a document, including this one.

---

## 🚀 Quick start

```bash
git clone https://github.com/SHADE-glitch/AgentOS && cd AgentOS
python3 -m pytest                       # 502 passed — the suite is the specification
node --test tests/js/plugin.test.mjs    # 29 pass  — the host seam

./bin/aos doctor --json                 # what this checkout has actually done
./bin/aos memory seed                   # a fresh store recalls nothing until this runs
./bin/aos run "add a /health endpoint" --cwd /path/to/project --provider test_provider
./bin/aos review list                   # the human gate: what approval would do
```

A fresh store is empty, so recall is empty, so nothing is ever proposed: `memory seed` is step one,
not a nicety.

<details>
<summary><strong>🔌 Speaking the contract from a host</strong></summary>

```bash
echo '{"schema_version": "1.2", "phase": "preflight", "task": "…", "session_id": "…", "cwd": "…"}' \
  | ./bin/aos preflight --payload-stdin
```

`memory.injection.text` is the ready-to-append `<agent_os>` block; an empty string means push nothing.

</details>

---

## 🏗️ Layout

```text
AgentOS/
├── bin/aos                     # thin shim -> python3 -m aos.cli
├── aos/                        # the engine — stdlib only
│   ├── config.py               # every path injectable; nothing else hardcodes a location
│   ├── contract/               # frozen preflight/postflight shapes, schema_version = "1.2"
│   ├── core/routing/           # hybrid router, role catalog, taxonomy
│   ├── core/memory/            # store · retrieve · record · evolve(gate) · policy · conflict
│   │                           #   inject (the block renderer) · authoring ·
│   │                           #   external (read-only neighbour recall) ·
│   │                           #   external_write (publish one approved lesson, via CLI)
│   ├── core/loop/              # state machine, lifecycle, stages, pending-postflight
│   ├── core/validation/        # build detection + code validation (runs each command once)
│   ├── core/evidence/          # collection, recovery planning (plan-only), provenance
│   ├── adapters/               # host_delegate · test_provider
│   └── cli/main.py             # doctor preflight postflight route run pending backfill memory review
├── integrations/opencode/      # the plugin, its fixture tests, and the live-run rig
├── content/                    # JSON you may edit without touching code (policies, seed)
├── store/                      # runtime state — gitignored, and never written by a test
├── docs/                       # architecture · decision · research · experiment · plan
└── tests/                      # pytest (hermetic tmp store) + tests/js/ (node --test)
```

| Document | What it holds |
|---|---|
| [`AGENTS.md`](AGENTS.md) | The non-negotiable checks — read this first if you or an agent is editing |
| [`docs/architecture/agent-os-v2.md`](docs/architecture/agent-os-v2.md) | §12 defect register (A–AS), §15 how far the evidence goes, §16 capability boundary |
| [`docs/decision/positioning.md`](docs/decision/positioning.md) | §5 what the neighbour note tool is · §6 the stop/degrade criteria |
| [`docs/plan/final-plan.md`](docs/plan/final-plan.md) | §11 the execution log — mostly a record of what went wrong and how it was caught |
| [`docs/experiment/`](docs/experiment/) | Frozen experiment, Stage 0 tickets, Stage 1 usage ledger |

---

## 🔒 The frozen contract (`schema_version = "1.2"`, serves `1.0` and `1.1`)

The preflight/postflight JSON shapes **are** the public interface. They live in `aos/contract/` and
`tests/test_contract.py` holds the 1.0 field set as a literal and asserts equality with what is
emitted — so a key cannot be dropped and cannot be added quietly. A version the engine does not
speak is **rejected** (exit `3`, fallback document) rather than answered in the engine's own version.

**`postflight` is where the learning signal arrives**, and it is the field set a host must not
short-change: `outcome`, `quality_score`, `test_exit_code` / `compile_exit_code`, `expected_files`,
`validation_status`, `tool_errors`, `session_error`, `user_interrupted`, `response_summary`,
`tool_trace`, `tool_calls`, `memory_retrieved`, `memories_used`, `files_changed`, `todos_unfinished`,
`reason`. With no outcome reported the loop is recorded `partial`, never `success`; any field the
engine does not read comes back named in `warnings` instead of being ignored in silence.

---

## 🗳️ Memory and the gate

`store/aos.db` is the single source of truth (schema `v5`, append-only migrations). A memory has
four separate axes — collapsing any two of them is how a store becomes noise:

| Axis | Values | Decides |
|---|---|---|
| `type` | `episodic` `semantic` `procedural` `failure` `preference` `constraint` | how it is **worded** in the block |
| `evidence_level` | `hypothesis` → `benchmark_evaluated` → `runtime_validated` → `independent_validated` → `real_project_validated` → `production_validated` | how far it has been **checked** |
| `status` | `candidate` `active` `verified` `deprecated` `superseded` `invalidated` `archived` | where it is in its **life** |
| `scope` | `global` `project:<id>` `session:<id>` | where it may be **recalled at all** |

Retrieval is deterministic (tag / domain / role / keyword overlap, a type bonus, decay applied, the
query logged). Thresholds live in `content/policies/*.json` — there are **eight** policy files, each
key-for-key equal to the built-in defaults, merged as "file overrides default": `decay` `external`
`external_write` `injection` `outcome` `promotion` `rejection` `retrieval`. Retuning a gate is an
edit, not a code change; the measured cost of the one external call the engine makes is **8.1**–9.2 s
per spawn, which is why it never sits on a hot path (the preflight budget is **1200** ms and a slow
engine is killed and simply injects nothing).

```bash
./bin/aos review list                                   # each row says what approving would do
./bin/aos review label <id…> --outcome failure --skill bugfix
./bin/aos review approve <id> --title T --body B --when W --tags A,B
                                                        # create only: the reviewer writes the
                                                        # 「因为」 no signal can supply, and names
                                                        # the subject that makes it findable again
./bin/aos memory retire <id> --reason R                # out of recall; row and history stay
```

`AR` and `AK` are the two open defects a newcomer will notice first — see
[`README` → Contributing](#-contributing) below and §12 of the architecture doc.

---

## ⚙️ Configuration

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
| session id / routing registry | `AOS_SESSION_ID` · `AOS_REGISTRY_PATH` | generated · built-in |

`AOS_BM_BIN=""` switches publishing off; so does `"enabled": false` in
`content/policies/external_write.json`. Neither changes what the gate decides: the store is written
first and remains the only thing recall reads.

---

## 🧪 Tests

```bash
python3 -m pytest                              # 502 passed
node --test tests/js/plugin.test.mjs           # 29 pass / 0 fail
```

Two traps that already cost this project time:

* **Do not append `-q` to pytest.** `pyproject.toml` sets `addopts = "-q"`; a second `-q` deletes the
  summary line, so `pytest -q | grep passed` prints nothing and a counting script reads zero.
* **Do not run `node --test tests/js/`.** That executes `fake-aos.cjs` as a test and reports
  `# tests 1 / # fail 1` — a red that means nothing.

`python -m unittest discover -s tests` collects **zero** tests and exits `0`: pytest is the only
runner, because the suite is built on fixtures. Every test runs against a hermetic `tmp_path` store,
and `AOS_BM_DB` / `AOS_BM_CONFIG_DIR` / `AOS_BM_BIN` point at paths that do not exist, so no test can
read — or publish into — a real notebook. The rig has its own 15 cases
(`integrations/opencode/live/tests`).

---

## 🤝 Contributing

Read [`AGENTS.md`](AGENTS.md) first. Its rule for a change: **one change = one commit**, and a report
with five items — files touched · test counts before/after plus new case names · behaviour
before→after *including what was deliberately left unchanged* · risk and rollback (single-commit
revertable) · whether the contract broke. If you skip a step, prove the step is still executable.

**Five failure modes** account for most of the defect register. Each has a guard, and each guard is
why a "small addition" is usually the bug: declared-but-never-written · written-but-never-read ·
read-but-never-assigned · display-disagrees-with-execution · proven-only-in-a-fixture.

Good places to start, with the reason each is still open:

| Item | Status | Why it is not a quick fix |
|---|---|---|
| `AR` run driver | open | The host exposes no field for it (`OPENCODE_CLIENT` is assigned only `"acp"`; the TUI never writes it, so human and agent both read `cli`). Adding a `source` today would be fabricating data; it needs a contract change and the owner's decision |
| `AK` interruptions | open | `user_interrupted` is read by the contract and the synthesiser, and nothing ever assigns it — the veto cannot fire. Needs a host event source |
| `AI` exit-code attribution | open | `metadata.exit` is visible, but mapping it to "this was a build / this was a test" is a judgement the plugin must not guess (self-grading, defect `F3`) |
| `AS` pending ledger | open | Crash records are keyed per session and only a postflight clears them, so `outstanding` is a **lower bound**: 66 unreported loops left one file |
| Vestigial columns | open | `use_count` / `success_count` / `last_used_at` are read by the CLI and by ranking reasons but **no code path writes them**, which leaves one branch in `retrieve.py` unable to fire |
| Expiry vs re-verification | open | `revalidate_after` has exactly one writer (the author's flag) while `expire_due` acts on it, so a re-verified memory can still expire on a date set at birth |
| Note-ownership seam | open | Recall skips notes whose parsed frontmatter carries the marker; untested paths are frontmatter that fails to parse (reads as a human note) and a human deleting the marker |
| Phase 2 | designed, not started | Constraints measured here: a spawn is 8.1–9.2 s against a 1200 ms budget, `retrieve()` ~1 ms, and the neighbour's **index lags its files** — so "text lives in basic-memory" has to say whether it reads files or a stale index |

What this project will not take, however good it looks: a second skill system, a telemetry writer,
MCP, third-party dependencies, orchestration, session retrieval, code indexing, an engine that edits
code, or anything that writes `~/.config/opencode/**`.

## 🔐 Privacy and placeholders

This repository is public and was scrubbed: no session text, no prompt bodies, no tool output, no
notebook titles, no machine paths. Documents describing real runs use placeholders instead, so the
numbers and the causality survive while the address book does not:

| Placeholder | Means |
|---|---|
| `<repo>` | the checkout of this repository |
| `<subject-project>` | the project a live run was performed against |
| `<rig>` / `<rig>-void` | scratch dirs for experiment scaffolding and sealed, voided attempts |
| `<bm-vault>` | the note folder read-only neighbour recall points at |
| `ses_redactedNN` | an anonymised host conversation id; distinct ids stay distinct |

Enforced rather than promised: `tests/test_readme_bilingual.py` fails if either README regains an
absolute home path or a session id, and the store (`*.db`, `loops/`, `evidence/`,
`pending-postflight/`) is gitignored — `git ls-files store` should list only `store/.gitignore`.

## ⚖️ License

[MIT](LICENSE) © 2026 SHADE-glitch.
