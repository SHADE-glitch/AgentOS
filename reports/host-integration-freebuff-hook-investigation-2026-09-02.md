# Host Integration Investigation — Freebuff CLI AOS Hook Not Effective (2026-09-02)

## Executive Summary

The AOS "Option C" integration for Freebuff CLI (automatic prompt injection via a
`UserPromptSubmit` hook in `~/.config/manicode/settings.json`) **does not and cannot
work with the installed Freebuff CLI v0.0.165**. Two independent root causes:

1. **The Freebuff binary has no hook runner.** A full `strings` scan of
   `~/.config/manicode/freebuff` (680k strings) finds **zero** occurrences of
   `UserPromptSubmit` / `prompt_submit` / Claude-style hook names. The binary
   never executes external scripts on prompt submission, so the hook can never fire.

2. **The settings sanitizer strips custom keys.** Freebuff's settings reader
   (`gP$` in the bundled JS) copies only a whitelist of known keys (`mode`,
   `adsEnabled`, `freebuffModel`, `freebuffReasoningEfforts`, …) into a new object.
   The `hooks` / `env` keys written by `install.sh` are **dropped on the next
   settings save**, confirmed before/after file mtimes.

The hook scripts themselves work when invoked directly (manual smoke test logged
`HOOK_TRIGGERED` + `AOS_CONTEXT_INJECTED len=285`), which is why the log file
"only has test entries" — no Freebuff CLI prompt has ever been able to trigger them.

## Symptom

- User configured Freebuff for AOS per `runtime/hosts/freebuff/README.md` /
  `install.sh`.
- `/tmp/aos_hook_log.txt` contains only:

  ```
  2026-09-02 08:59:23 HOOK_TRIGGERED: {"prompt": "final verification", "cwd": "/tmp"}
  2026-09-02 08:59:25 AOS_CONTEXT_INJECTED: len=285
  ```

- Real Freebuff CLI usage afterwards adds nothing to the log and shows no AOS
  context.

## Evidence

### 1. The 08:59 log lines are a manual test, not CLI output

`prompt_submit.sh` reads its input with `INPUT=$(cat)` and expects
`{"prompt": ..., "cwd": ..., "session_id": ...}` on stdin. The logged payload
(`{"prompt": "final verification", "cwd": "/tmp"}`) is exactly the script's own
stdin contract — a hand-piped smoke test of the hook chain
(`prompt_submit.sh → aos_bootstrap.py → aos_host_adapter.py`), which succeeds.
The Freebuff CLI has no code path that invokes this script.

### 2. Freebuff binary (v0.0.165) contains no hook mechanism

```
$ strings ~/.config/manicode/freebuff > /tmp/fb_strings.txt   # 680,336 lines
$ grep -c "UserPromptSubmit" /tmp/fb_strings.txt   → 0
$ grep -c "prompt_submit" /tmp/fb_strings.txt      → 0
$ grep -c "PreToolUse|PostToolUse|SessionStart"    → 0/0/1 (embedded lib noise)
$ grep -c "config/opencode" /tmp/fb_strings.txt    → 0  (not an opencode fork)
```

The app is a Bun-bundled binary (`bun:wrap`, `bun:afterUpdate` present) that reads
only `~/.config/manicode/settings.json` (confirmed: `TLA() → join(aM(), "settings.json")`).
`install.sh`'s comment about a `launcher.js` beside the binary is stale — the
launcher is `~/.npm-global/bin/freebuff` (a Node `createLauncher` shim) and the
binary lives at `~/.config/manicode/freebuff`.

### 3. Settings whitelist wipe (mtime evidence)

| time (CST) | file | event |
|---|---|---|
| 08:59:23/25 | `/tmp/aos_hook_log.txt` | manual hook test OK |
| 09:04:38 | `~/.config/manicode/settings.json` | **rewritten WITHOUT `hooks`/`env`** |
| > 09:04:38 | `/tmp/aos_hook_log.txt` | no new entries ever |

`settings.json` after the wipe contains only `mode`, `adsEnabled`,
`freebuffModel`, `hasSubmittedFirstPrompt` — exactly the sanitizer's whitelist,
proving the app (not the user) removed the AOS keys.

## Root Cause

The Freebuff host adapter assumed a hook mechanism ("Option C", auto prompt
injection) that **does not exist in Freebuff CLI v0.0.165**. Even if a future
version adds it, settings.json is a poor carrier because Freebuff rewrites the
file from its own in-memory model and discards unknown keys.

## Impact

- Freebuff CLI: AOS decision context is **never injected**. There is currently no
  supported extension point (no hooks, no plugins, no opencode.jsonc support).
- Freebuff Desktop: unaffected either way — it never reads local settings hooks.
- OpenCode host plugin: **unaffected and still the only working AOS integration**
  (`~/.config/opencode/opencode.jsonc` → `/home/shade/.agents/runtime/hosts/opencode/plugin`).

## Recommendations

1. Treat Freebuff CLI integration as **unsupported on v0.0.165**; keep the hook
   scripts for manual/testing use only (documented in README + detected by
   `install.sh`'s compatibility check).
2. Use the OpenCode plugin for AOS decision support; works today.
3. Re-evaluate when a Freebuff release ships real hooks/plugins — then wire AOS
   through that official mechanism instead of settings.json.
4. If manual injection outside the CLI is required, wrap the
   `~/.npm-global/bin/freebuff` launcher to prepend AOS context to one-shot
   prompts (needs explicit user opt-in; invasive).

## Verification Path (for future checks)

```bash
# 1. Does the binary support hooks?
strings ~/.config/manicode/freebuff | grep -c UserPromptSubmit   # 0 = unsupported

# 2. Is the hook still in settings.json?
grep -c hooks ~/.config/manicode/settings.json

# 3. Manual hook chain test (NOT via CLI — proves scripts only):
printf '{"prompt":"smoke test","cwd":"/tmp"}' \
  | bash ~/.agents/runtime/hosts/freebuff/hooks/prompt_submit.sh | head -c 300
```