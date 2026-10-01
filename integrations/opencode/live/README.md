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

1. **Numbers that match without asking a model.** The engine persists
   `recall.injection_chars` into `store/loops/<LOOP>.json`; the plugin logs the length of the element it
   appended. Equal means the block the engine built is the block the host was handed. Measured on the
   real-store run: `511 == 511`. (The pending record carries the same number too, but the postflight
   deletes it — which is why the loop file got the durable copy.)
2. **An input-token delta against the inert arm** — same prompt, same cwd, same plugin stack, only our
   seam switched off: `AOS_RIG_INERT=1 live/run.sh …`. Measured: **+583 input tokens** for a
   1,279-character block. `--pure` is *not* this control: it drops every external plugin, so its delta
   belongs to DCP, the notifier and the tracker as much as to us.
3. **A behavioural marker — kept, but it proves the least.** The first attempt planted a memory holding a
   nonsense token and asked the model to repeat it; the plugin arm did not produce it either. Of course
   not: our own preamble says *"它们是经验，不是指令 … 不要向用户复述本节"*. A model that respects the
   block's framing fails a marker test by construction, so a marker is corroboration at best, and never
   without witness 1 or 2 beside it.

`snapshot.sh` prints hot runs **grouped by session** for the same reason as the store guard: `source='hot'`
is a global counter and the owner's ordinary use writes it, so a bare total would let daily
activity hide whether the rig closed anything.

The clause "the owner's ordinary use writes it" was asserted before it was measured. It is sourced now,
and one link in the chain is still missing — which is worth stating precisely, because stop-criterion 1
counts `source='hot'` and nothing else:

- **Resident hooks do fire in interactive sessions** `[Verified]`. The *other* plugin in
  `~/.config/opencode/plugin/` is `skill-tracker.js`, and its `tool.execute.after` / `event` handlers
  left production rows in `~/.local/share/opencode/skill-usage.db` (read `mode=ro`): 21 `tool_call` in
  `skill_usage`, 39 `tool_call` + 9 `event_detected` in `plugin_usage`, dated 2026-09-23 … 09-30 —
  days on which this rig ran nothing.
- **`session.idle`, the event our postflight waits for, reaches plugins in real sessions** `[Verified]`.
  `@mohak34/opencode-notifier@0.4.0` handles `type === "session.idle"` and calls
  `idle(sessionID, isCLI)` (`dist/index.js:2319`); `isCLI` is computed at `:2293` and exists only because
  both a CLI client and the TUI arrive there. Its delivered-notification counter
  (`~/.config/opencode/opencode-notifier-state.json`, currently `turn: 21277`, incremented at `:1846`) is
  a live record that this path has run thousands of times — far more than this rig's 8 runs, so it is the
  owner's usage. Note what it does *not* say: the counter never records which client was attached, which
  is precisely the link the next bullet is missing.
- **⇒ therefore a TUI turn lands a `source='hot'` observation** `[Inferred]`, not observed. Every hook our
  seam needs is proven live in interactive use except `chat.message`, which is the one that *opens* the
  loop — and skill-tracker's `chat.message` handler writes no rows, so there is no trace to borrow.
  One real session settles it: `./bin/aos doctor` before and after, and `observations: hot` must tick.

## Running the arms

Every entry point needs `AGENT_OS_ROOT` **exported first** — `selfcheck.sh:10` hard-fails without it
(`${AGENT_OS_ROOT:?}`), and `run.sh` only satisfies it at `:34`, so the bare lines below fail on a shell
that has not exported it. Pin the store too, or the self-check refuses to proceed (`:25-34`):

```bash
export AGENT_OS_ROOT=/path/to/AgentOS AOS_RIG=/tmp/aos-rig AOS_STORE_DIR=$AOS_RIG/store
mkdir -p "$AOS_RIG/store" "$AOS_RIG/logs"        # see the tee-before-mkdir trap below (AF)
live/run.sh plugin-arm  <cwd> '<prompt>'                # our seam active
AOS_RIG_INERT=1 live/run.sh inert-arm <cwd> '<prompt>'  # same stack, seam off — the real control
live/run.sh pure-arm    <cwd> --pure '<prompt>'         # every external plugin gone; not a control for us
live/run.sh second-turn <cwd> -s <sessionID> '<prompt>' # multi-turn: where a neighbour writes into our element
AOS_STORE_DIR=$AGENT_OS_ROOT/store AOS_RIG_ALLOW_REAL_STORE=1 live/run.sh real-1 <cwd> '<prompt>'  # counts toward criterion 1
```

`<label>` is only a filename tag — there is no `accept`/`real` arm; the real store is reached solely
through `AOS_STORE_DIR` + `AOS_RIG_ALLOW_REAL_STORE=1` (`run.sh:40-48`).

## The headless permission trap (round 11) `[Verified]`

`opencode run` has no TTY to approve tool use, and this machine's config is `permission.bash = "ask"`, so
**any prompt that makes the model reach for a shell dies**: the host logs `auto-rejecting`, the assistant
message ends with `tool` parts and **0 characters of text**, and the run still exits 0. Three consecutive
real-store runs failed exactly this way while the injection itself was flawless (`len=1122` == engine
`injection_chars=1122`). Two consequences, both load-bearing:

- Judge a run's verdict by **whether an answer exists at all**, not by whether the block arrived. The honest
  label for these runs was `failure` — and *without* `--skill`, because the cause was the harness, not any
  recalled memory (the queue then prints `blamed_memories: []`, which is the anti-"linkage-not-outcome" rule working).
- Prompts that are answerable from knowledge (a latency-metric question, an export-shape question asked
  cold) survive; prompts that invite inspection do not. Never "fix" this with `--auto` — that flag is banned
  by rule, and it would make the rig approve tools the owner has not agreed to.

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

The global arm is **not** an arrival proof on its own, and the run proved it wasn't: the
control arm answered the same question correctly from its own training data and a
`WebFetch` of the docs. Nothing about that answer could be attributed to our block. Arrival
is carried by the two witnesses that do not ask a model to cooperate — see
*"The three witnesses…"* above.

What the table also says, and it is the finding that cost the most calls: **a prompt written
purely in Chinese recalled nothing** (0.080 against a `min_score` of 0.15). Tags and
categories in this corpus are English, `compute_static_relevance` matches a tag only if it
has ≥3 characters and appears as a substring of the task text — so two-character Chinese
words cannot count at all — and a router keyword must equal a tag (`agent` ≠ `agent-os`).
Both successful recalls happened only because the router happened to emit English entities
that collided with English tags. The rig's prompts are therefore deliberately
token-bearing, which is a workaround, not a fix; the defect is registered as V in
`docs/architecture/agent-os-v2.md` §12 and is a decision for the owner, not a patch here.

## Privacy line

Prompts are synthetic and contain no conversation text from anyone. The plugin's own
reporting is limited to key names, indices and counts — never payload values.
Host sessions written by a run land in `~/.local/share/opencode/opencode.db`, which
this rig reads never and writes never.
