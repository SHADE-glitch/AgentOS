# MAINTENANCE.md — AgentOS

Procedure file. This is a **router**: the rules for working in this repository live in
[`AGENTS.md`](AGENTS.md), and the long-form design, plan and evidence live under [`docs/`](docs/).
Do not duplicate their tables here — a duplicated fact is the thing that drifts.

The one maintenance risk that matters: **opencode changing its host contract**. The plugin enters
only through `bin/aos` + a stdin/stdout JSON contract and only pushes its own `output.system`
elements; if the host renames a hook, changes the `output.system` shape, or starts writing
`OPENCODE_CLIENT`, the plugin can silently no-op or misbehave while CI stays green (CI runs only the
offline layer and never the real host). The rules and the red lines are in
[`AGENTS.md`](AGENTS.md) under "Non-interference" and "Real-machine testing".

## Verification tiers
- **L0** — `python3 -m pytest` and `node --test tests/js/plugin.test.mjs` (temp store, no host).
- **L1** — the full engine path against a scratch store (`AOS_STORE_DIR` / `AOS_DB_PATH` /
  `AOS_BM_DB` all pointed at scratch).
- **L2** — the real host (opencode TUI) and the real store; needs the owner's go-ahead and a
  recorded approval scope.

## CI
`.github/workflows/ci.yml` runs the offline layer on a Python 3.11 / 3.14 matrix, plus the JS plugin
tests on Node 20. See `AGENTS.md` § CI.

## Assets
| Document | Read it when |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Before any edit — the non-negotiable checks |
| [`docs/architecture/agent-os-v2.md`](docs/architecture/agent-os-v2.md) | Judging behaviour, defect ids (§12) or how far something is proven (§15) |
| [`docs/plan/final-plan.md`](docs/plan/final-plan.md) | Reviewing how recent rounds went wrong and were fixed (§11) |
| [`integrations/opencode/live/README.md`](integrations/opencode/live/README.md) | Running on the real machine, or checking the privacy line |
