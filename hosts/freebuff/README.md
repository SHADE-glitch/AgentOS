# AOS Host Adapter for Freebuff

Agent OS (AOS) integration for Freebuff via **automatic prompt injection** (Option C).

> ## ⚠ Compatibility Status (verified 2026-09-02)
>
> **Freebuff CLI v0.0.165 does NOT support `UserPromptSubmit` hooks.** The binary
> (`~/.config/manicode/freebuff`) contains no hook runner at all
> (`strings` scan: 0 occurrences of `UserPromptSubmit` / `prompt_submit`), and its
> settings reader **discards unknown keys** (`hooks` / `env`) on the next settings
> save — verified: the app rewrote `~/.config/manicode/settings.json` without them
> at 09:04:38, minutes after a manual test injected them.
>
> **Consequences:**
> - Freebuff CLI will **never execute** `prompt_submit.sh` on its own.
> - Adding the hook via `install.sh` is pointless on this version: it gets stripped.
> - The hook scripts still work **when invoked directly** (manual testing only).
> - The only working AOS host integration today is the **OpenCode plugin**
>   (`~/.config/opencode/opencode.jsonc` → `runtime/hosts/opencode/plugin`).
>
> Full evidence: `reports/host-integration-freebuff-hook-investigation-2026-09-02.md`
> Re-check support with: `strings ~/.config/manicode/freebuff | grep -c UserPromptSubmit`

## Architecture

```
User submits prompt in Freebuff CLI
  ↓
Freebuff UserPromptSubmit hook fires   ← NOT SUPPORTED on v0.0.165
  ↓
prompt_submit.sh (bash hook)
  ↓
aos_bootstrap.py (Python)
  ↓
aos_host_adapter.py → Router / Memory / Orchestrator
  ↓
Returns decision context (classification, memory, routing)
  ↓
Context prepended to prompt
  ↓
Freebuff agent executes with AOS context
```

## Installation

```bash
bash ~/.agents/runtime/hosts/freebuff/install.sh
```

`install.sh` performs a **compatibility check** first:

- If the binary shows `UserPromptSubmit` support → full install (scripts +
  settings hook).
- If unsupported (v0.0.165 and earlier known-bad) → copies the hook scripts for
  manual/testing use only and **skips** the settings.json modification, printing a
  banner. Use `--force` if you still want the settings hook written anyway.

## Configuration

**Freebuff CLI** reads its config from `~/.config/manicode/settings.json`
(binary at `~/.config/manicode/freebuff`, launched via the Node shim
`~/.npm-global/bin/freebuff`).

The installer adds a `UserPromptSubmit` hook that intercepts every prompt and
injects AOS context — **provided the binary supports it**.

## How It Works

1. Freebuff's `UserPromptSubmit` hook fires on every prompt *(would fire — binary
   currently lacks this mechanism)*
2. Hook calls `aos_bootstrap.py` → `aos_host_adapter.py`
3. AOS returns classification, memory, routing, warnings, instructions
4. Context is prepended to the user's prompt
5. Freebuff agent executes with AOS context

## What Gets Injected

- **Task classification** (category, difficulty, domains)
- **Recommended role** (e.g., backend-architect, security-engineer)
- **Relevant memories** (past decisions and patterns)
- **Safety warnings** (destructive actions, sensitive data)
- **Execution instructions** (role-based guidance)

## Files

| File | Purpose |
|------|---------|
| `aos_bootstrap.py` | Python backend — calls AOS adapter, formats context |
| `hooks/prompt_submit.sh` | Bash hook — intercepts prompt, injects context |
| `settings.json` | Config template (for reference, not directly installed) |
| `install.sh` | Installation script with compatibility check |

## Uninstall

```bash
bash ~/.agents/runtime/hosts/freebuff/install.sh --uninstall
```

Or manually remove the `UserPromptSubmit` entry from `~/.config/manicode/settings.json`.

## Verification

The hook chain **by itself** works and can be smoke-tested directly
(this does NOT go through the Freebuff CLI):

```bash
printf '{"prompt":"smoke test","cwd":"/tmp"}' \
  | bash ~/.agents/runtime/hosts/freebuff/hooks/prompt_submit.sh | head -c 300
cat /tmp/aos_hook_log.txt   # look for HOOK_TRIGGERED / AOS_CONTEXT_INJECTED
```

> ⚠ If the log only ever contains manually-piped entries, that is expected:
> Freebuff v0.0.165 cannot trigger the hook itself (see Compatibility Status).