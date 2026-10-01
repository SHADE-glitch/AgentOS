# Live rig — driving one real host run, then reading what it left

Nothing here is engine capability. `aos/` never invokes opencode (that reverse path
was deleted in P1, and `tests/test_skill_boundary.py` fails the build if the literal
`opencode run` appears in engine or test sources). These two scripts are a **test
harness**: a person, or an agent acting as one, runs them to find out whether the
installed plugin actually closes the loop.

## Usage

```bash
live/selfcheck.sh                             # before spending any model call
live/snapshot.sh <label>                      # read-only store + engine snapshot
live/run.sh <label> <cwd> [flags] '<prompt>'  # selfcheck, snapshot, one host run, snapshot
```

Flags passed through to the host: `--pure` (no external plugins — the control arm)
and `-s <sessionID>` (continue a session, which is how the multi-turn case is reached).

Environment: `AOS_RIG` (default `/tmp/aos-rig`), `AOS_STORE_DIR` / `AOS_DB_PATH`
(default a scratch copy under `$RIG/store`), `AGENT_OS_ROOT` (default this checkout).

`run.sh` **refuses to run when `AOS_STORE_DIR` points at the real store**. The plugin
spawns `bin/aos`, which inherits this environment, so an unpinned store would let a
test run write the very rows stop-criterion 1 counts. The one deliberate exception is
the final acceptance run, which sets `AOS_RIG_ALLOW_REAL_STORE=1` and says so out loud.

## The three witnesses that the injection actually arrived, in order of trust

1. **Numbers that match without asking a model.** The engine's
   `store/pending-postflight/pending-<session>.json` carries `injection_chars`; the
   plugin's stderr records the length of the element it appended. Equal means the block
   the engine built is the block the host was handed.
2. **A behavioural marker, only valid against a `--pure` control in the same cwd.** If the
   control arm answers too, the answer came from the model or the filesystem and the arm
   proves nothing — discard it. (This is why "ask about the plugin export rule and see if
   it answers" is *not* a proof when the working directory is this repository: the rule is
   in `plugin/agent-os.js` and in this README, right there for the taking.)
3. A marker memory planted for the scratch copy only, never in the real store.

`snapshot.sh` prints hot runs **grouped by session** for the same reason: `source='hot'`
is a global counter and ordinary TUI use writes it, so a bare total would let daily
activity hide whether the rig closed anything.

## Why each piece is the way it is

- **`command opencode`, and never `--auto`.** The owner's alias carries `--auto`
  (auto-approves tool permissions) and yargs does not treat `opencode help run` as
  help — it started a real agent that ran three bash commands. Prompts here need no
  write or exec permission; a permission prompt stops that turn, which is evidence
  rather than a failure.
- **`AGENT_OS_ROOT` is exported by the script, not inherited.** Unset, the plugin
  loads and does nothing — indistinguishable from "the plugin is broken", which is
  the one misdiagnosis that would waste the whole exercise.
- **Snapshots open the store `mode=ro`.** A diagnostic that mutates what it measures
  turns a test run into a real one silently.
- **Plugin observability is stderr only.** `AOS_PLUGIN_DEBUG=1` makes the plugin speak
  to stderr, and `--print-logs` carries it into the log file. The plugin writes no
  files — that property is asserted by `tests/js/plugin.test.mjs`, and adding a trace
  file would break it and weaken the withdrawal contract ("the only thing written is
  `store/`"). The rig writes the file, not the plugin.

## The two frozen prompts, and what they select

Recall is filtered by scope (P2), so the arm's working directory decides which
memories can appear at all. Scores below are `final_score` against the 13 seeds with
`min_score = 0.15`, measured offline:

| arm | cwd | prompt | expected hits |
|---|---|---|---|
| global | outside the checkout | `opencode plugin 的 export 应该怎么写，loader 会不会把每个 export 当工厂` | `M-SEED-PHASE010` 0.384, `M-SEED-EXPORT8` 0.292, `M-SEED-NOVERDIT7` 0.183 |
| project | `<checkout>` | `修复 cache key 碰撞导致命中率下降的 bug` | `M-SEED-CACHEKEY02` 0.446, `M-SEED-MIGRATE11` 0.35, `M-SEED-DEFAULT5` 0.35 |

The global arm doubles as the **arrival proof**: `M-SEED-EXPORT8` is the only memory
that states the plugin export rule, so a host answer containing it proves the block
reached the model — and `--pure` on the same prompt must not produce it.

Note what the table also says: a prompt written purely in Chinese recalled **nothing**
(`M-SEED-*` tags and categories are English, and `compute_static_relevance` matches
tags as substrings of the task text). The rig prompts are therefore deliberately
token-bearing; that is a corpus/ranking limitation, recorded separately, not something
this harness hides.

## Privacy line

Prompts are synthetic and contain no conversation text from anyone. The plugin's own
reporting is limited to key names, indices and counts — never payload values.
Host sessions written by a run land in `~/.local/share/opencode/opencode.db`, which
this rig reads never and writes never.
