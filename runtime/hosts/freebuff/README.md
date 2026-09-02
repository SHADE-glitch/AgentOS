# AOS Host Adapter for Freebuff

Agent OS (AOS) integration for Freebuff via **automatic prompt injection** (Option C).

## Architecture

```
User submits prompt in Freebuff CLI
  ↓
Freebuff UserPromptSubmit hook fires
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

## Configuration

**Freebuff CLI** reads its config from `~/.config/manicode/settings.json`.

The installer adds a `UserPromptSubmit` hook that intercepts every prompt and injects AOS context.

## How It Works

1. Freebuff's `UserPromptSubmit` hook fires on every prompt
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
| `install.sh` | Installation script |

## Uninstall

```bash
bash ~/.agents/runtime/hosts/freebuff/install.sh --uninstall
```

Or manually remove the `UserPromptSubmit` entry from `~/.config/manicode/settings.json`.

## Verification

After installing, send a prompt in Freebuff CLI and check:

```bash
cat /tmp/aos_hook_log.txt
```

Look for `HOOK_TRIGGERED` and `AOS_CONTEXT_INJECTED` entries.
