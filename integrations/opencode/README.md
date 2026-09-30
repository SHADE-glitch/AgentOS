# OpenCode integration — advisory plugin

**Status: written, tested against fixtures, and not installed.** Nothing in this
directory is loaded by opencode until the file is placed under
`~/.config/opencode/plugin/`, and this repository never does that. Installing it
is a separate decision with its own gate (`docs/plan/final-plan.md` §5, §6): the
fixture suite proves non-interference, but hook ordering and the shape of a real
`tool.execute.after` payload can only be confirmed by loading it, and that is not
done here.

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
| additive-only | our element is appended; nobody else's is edited, reordered, or dropped; index 0 is never taken | same file — `system.slice(0, n) == base`, length `n+1`, and a named comment on why `[0]` matters (`@tarquinen/opencode-dcp` reads it to decide whether a call is internal and skips its pruning pass entirely) |
| reuse-not-rebuild | reads nothing of another component's; writes nothing outside `store/`; the session→loop lookup goes through `aos pending`, not through someone's file format | the last case in the JS suite plus `tests/test_pending.py` on the Python side |

Run them:

```bash
python3 -m pytest                          # includes tests/js via node --test
node --test tests/js/plugin.test.mjs       # the plugin half on its own
```

`test_the_plugin_test_suite_runs_and_passes` fails when node is absent rather than
skipping: a guard that skips is a guard that passed.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `AGENT_OS_ROOT` | *unset* | the checkout that owns `bin/aos`. Unset ⇒ the plugin is inert (that is the disable-clean case, not a misconfiguration) |
| `AOS_BIN` | `$AGENT_OS_ROOT/bin/aos` | the engine executable |
| `AOS_TIMEOUT_MS` | `1200` | per call. A slow engine means no injection this turn, never a blocked prompt |
| `AOS_PLUGIN_DEBUG` | *unset* | writes swallowed hook errors to stderr; off by default so a quiet failure never becomes a log line nobody reads |

## To install it, when that decision is made

```bash
ln -s "$PWD/integrations/opencode/plugin/agent-os.js" ~/.config/opencode/plugin/agent-os.js
```

with `AGENT_OS_ROOT` pointing at this checkout in the environment opencode runs in.
The load rule that this file respects: a plugin module must be
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
