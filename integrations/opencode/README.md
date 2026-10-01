# OpenCode integration — advisory plugin

**Status: installed on this machine (2026-10-01), with the owner's approval.**
This repository still never installs it — the install was one deliberate act by a
human, and it is two files, both reversible:

```
~/.config/opencode/plugin/agent-os.js -> <this checkout>/integrations/opencode/plugin/agent-os.js
~/.zshrc:87  alias opencode='AGENT_OS_ROOT=/home/shade/Public/AgentOS opencode --auto'
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
export AGENT_OS_ROOT=/home/shade/Public/AgentOS     # this machine: inlined into the opencode alias
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

## What is still `[Unconfirmed]`

- The order in which opencode runs several registered `system.transform` hooks.
  Appending is safe under any order; a *reorder* by another plugin is not something
  this code depends on, but it is also not verified.
- Whether a real `tool.execute.after` payload exposes an error the way the fixture
  assumes. The plugin counts only an error it can actually see and otherwise leaves
  `tool_errors` **absent** — an absent signal lowers the verdict's coverage, while a
  fabricated `0` would have claimed "nothing went wrong".
- Anything about a session that the plugin did not observe, which is why the
  restart path asks `aos pending` instead of guessing from files.
