# OpenCode integration — advisory plugin

**Status: installed on this machine (2026-10-01), with the owner's approval.**
This repository still never installs it — the install was one deliberate act by a
human, and it is two files, both reversible:

```
~/.config/opencode/plugin/agent-os.js -> <this checkout>/integrations/opencode/plugin/agent-os.js
~/.zshrc:87  alias opencode='AGENT_OS_ROOT=<repo> opencode --auto'
```

Nothing else under `~/.config/opencode/**` was touched: `opencode.json`,
`package.json`, the other plugin and every config file keep their pre-install
mtime and contents. Removing `AGENT_OS_ROOT` from that alias makes the plugin
inert again without deleting anything; removing the symlink uninstalls it. The
two facts that a fixture cannot prove — hook ordering against other plugins, and
the real shape of a `tool.execute.after` payload — are still `[Unconfirmed]`
until a real session runs; that is what loading it was for.

## What it does

Three hooks, one job each:

| Hook | Job |
|---|---|
| `chat.message` | send the task text to `aos preflight`, remember the loop for this session |
| `experimental.chat.system.transform` | **append** the `<agent_os>` block as its own element |
| `event` (`session.idle`, `session.error`) + `tool.execute.after` | accumulate signals, then `aos postflight` |

That is the whole surface. There is no tool registration, no permission hook, no
message rewriting, no second injection channel (`experimental.chat.messages.transform`
exists in the API and is deliberately unused, so there is exactly one place to audit).

## The three properties, and how they are proved

| Property | Meaning | Proof |
|---|---|---|
| disable-clean | with `AGENT_OS_ROOT` unset the plugin loads, does nothing, and `output.system` is byte-identical to the no-plugin case | `tests/js/plugin.test.mjs` — the array is compared to the fixture's own baseline and the fake engine records zero calls |
| additive-only | our element is appended; nobody else's is edited, reordered, or dropped; index 0 is never taken; and text another plugin appended **into our own element** is kept | same file — `system.slice(0, n) == base`, length `n+1`, and a named comment on why `[0]` matters (`@tarquinen/opencode-dcp` reads it to decide whether a call is internal and skips its pruning pass entirely). Plus `another plugin's text appended to our element survives us`, which replays DCP's actual write (`output.system[len - 1] += "\n\n" + prompt`) and asserts the suffix is still there byte for byte after our second transform — without that, our replace-in-place deleted a neighbour's prompt on the second LLM call of one session |
| reuse-not-rebuild | reads nothing of another component's; writes nothing outside `store/`; the session→loop lookup goes through `aos pending`, not through someone's file format | the last case in the JS suite plus `tests/test_pending.py` on the Python side. The zero-write half is stronger than a test: the plugin imports no write API at all (`existsSync` is its only `node:fs` use), and `the plugin has no way to write to the filesystem` asserts exactly that against the source |

Run them:

```bash
python3 -m pytest                          # includes tests/js via node --test
node --test tests/js/plugin.test.mjs       # the plugin half on its own
```

`test_the_plugin_test_suite_runs_and_passes` fails when node is absent rather than
skipping: a guard that skips is a guard that passed.

For the half a fixture cannot prove — a real host session through the installed
plugin — see [`live/README.md`](live/README.md). That directory is a test rig, not
engine capability: nothing under `aos/` invokes opencode, and the boundary guard
holds the engine to that rule.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `AGENT_OS_ROOT` | *unset* | the checkout that owns `bin/aos`. Unset ⇒ the plugin is inert (that is the disable-clean case, not a misconfiguration) |
| `AOS_BIN` | `$AGENT_OS_ROOT/bin/aos` | the engine executable |
| `AOS_TIMEOUT_MS` | `1200` | per call. A slow engine means no injection this turn, never a blocked prompt |
| `AOS_PLUGIN_DEBUG` | *unset* | records every hook to stderr — successes (`preflight ok loop=…`, `system appended index=… len=…`, `postflight sent …`) as well as swallowed errors. Every path fails open, so without it "the engine had nothing", "the hook threw" and "the plugin was inert" are the same silence. Records carry keys, indices and counts only — never a task or a memory body. |

## How it was installed (and how to undo it)

```bash
ln -s "$PWD/integrations/opencode/plugin/agent-os.js" ~/.config/opencode/plugin/agent-os.js
# and in the environment opencode runs in:
export AGENT_OS_ROOT=<repo>     # this machine: inlined into the opencode alias
```

Note the install did **not** use `opencode plugin <module>` — that subcommand also
rewrites `~/.config/opencode/opencode.json`, and the config file is not this
repository's to edit. The symlink plus one environment variable is the whole
installation, and the whole undo:

```bash
rm ~/.config/opencode/plugin/agent-os.js     # and drop the env prefix from the alias
```

The load rule this file respects: a plugin module must be
`export default { id, server }` — a bare function export makes opencode call every
export as a factory and abandon the load in silence.

## What a live run confirmed, and what still is not

A real host session ran through this seam on 2026-10-01 (rig: [`live/README.md`](live/README.md)).

- **Confirmed**: `tool.execute.after` hands us `output` with keys `attachments, metadata, output, title`
  — **no `error` key** — and a tool call whose permission was refused never reaches the hook at all.
- **Confirmed from the host's own typings, then used**: the same hook is handed `{tool, sessionID, callID, args}` (`@opencode-ai/plugin/dist/index.d.ts:249-258`). The plugin now reads `args` — and only the two keys `command` / `cmd` — to build a **normalised method label** (name-shaped tokens, ≤3 words, `-m` kept only for an interpreter, a quote ends the segment). The command itself is computed inside the host process and thrown away there: no path, argument, environment value or quoted text crosses the seam, and `metadata.exit` is recorded verbatim with no claim about whether the command was a build or a test (that mapping stays unapproved, defect AI).
  So `tool_errors` stays absent on this host, which lowers the verdict's coverage and sends the run to
  the human queue. That is the designed behaviour ("absent is not zero"), not a bug to patch by guessing.
- **Still unconfirmed**: the order in which opencode runs several registered `system.transform` hooks.
  Nothing here observed DCP writing to `system` at all, so the collision that defect R describes is
  proven against a fixture that replays DCP's own line of code, not against the live stack. Appending
  is safe under any order; the suffix-preserving replace is safe under the worst one.
- **Arrival is proven by numbers, not by obedience.** The first attempt planted a memory containing a
  nonsense token and asked the model to repeat it; it never did — our own preamble tells it
  *"不要向用户复述本节"*, so a model that behaves correctly fails that test by construction. What proves
  the block reached the request instead: the engine's persisted `injection_chars` equals the length the
  plugin logged (511 == 511), and an otherwise identical run with only our seam inert costs +583 input
  tokens for 1,279 characters of block. `--pure` is **not** a control for us: it removes every external
  plugin, so it measures DCP and the tracker as much as our own work.

## The exp-v1 real-host probe: the capture chain works on the actual host `[Verified]`

One run on 2026-10-01 (`opencode run --auto -m opencode/space-bunny-free`, smoke project under
`<subject-project>`, engine store pinned to an isolated directory by a single `AOS_STORE_DIR`,
`AOS_TIMEOUT_MS` left at its default) settled the four things the fixtures could not settle:

```text
tool.execute.after      5 bash steps, logged as key names only
  → args.command         present — the host's own persisted tool parts name the key `command`
  → method fingerprint   ls / pytest tests / python3 -m pytest probe_tests / cat / grep
  → entry.trace          ordered, bounded; `metadata.exit` recorded verbatim (0 / 4 / 0 / 0 / 0)
  → session.idle         fires in headless `run` mode:  postflight sent … answered=true
  → postflight           signals = tool_trace, tool_calls, response_summary
  → observation          signals_json.tool_trace survives; present lists it; needs_review=1
```

Two properties were proven by construction rather than by trust. A canary string existed only in a
project file and inside a quoted command argument: it is absent from the store, from our log lines,
from `review list` output and from this repository — the quote rule ended the fingerprint at `grep`,
so the command's content never left the host process. And three arms fed the same `test_exit_code`-free
signal set with, without a trace: `mass` was identical, which is the weight-0.00 pinning holding on
real data rather than in a unit test.

What the probe deliberately did **not** buy:

- Non-shell tools report no exit code (`glob` gives `count/truncated`), and the host hands no `error`
  key, so failures of edit/read tools stay invisible; `tool_errors` is absent on this machine, not zero.
- A tool call whose permission was refused never reaches the hook, so "that direction was rejected" —
  the most informative event — leaves no trace at all.
- A method switch the model only thinks about is unobservable; only executed steps appear.
- Each prompt opens a new loop and resets the accumulator, so a failure in turn 1 and a fix in turn 3
  are two trajectories that never meet.
- `exit=0` says the step returned 0, not that this step was the right method: the trace carries
  adjacency, never causality. Attribution still needs a human (`review approve --body`).

Freeze point, the frozen file list and the Verified / Unconfirmed split: `docs/experiment/exp-v1-baseline.md`.
