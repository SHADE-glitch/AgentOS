# AOS Host Adapter for Freebuff

Agent OS (AOS) integration for Freebuff via **automatic prompt injection** (Option C).

This is the same pattern as the OpenCode plugin — AOS context is automatically injected into every prompt without the agent needing to call any tools.

## Architecture

```
User submits prompt
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

**This is identical to how the OpenCode plugin works:**

| | OpenCode Plugin | Freebuff Hook |
|--|----------------|---------------|
| **Intercept** | `chat.message` hook | `UserPromptSubmit` hook |
| **Backend** | `aos_host_adapter.py` | `aos_bootstrap.py` → `aos_host_adapter.py` |
| **Inject** | `experimental.chat.system.transform` | Prepend to prompt |
| **Reliability** | Automatic, 100% trigger | Automatic, 100% trigger |

## Installation

```bash
# Global installation (applies to all Freebuff sessions)
bash ~/.agents/runtime/hosts/freebuff/install.sh

# Project-local installation (applies to current project only)
bash ~/.agents/runtime/hosts/freebuff/install.sh --local
```

## How It Works

1. **Interception**: Freebuff's `UserPromptSubmit` hook fires on every prompt
2. **Backend Call**: Hook calls `aos_bootstrap.py` which calls `aos_host_adapter.py`
3. **Decision Context**: AOS returns classification, memory, routing, warnings, instructions
4. **Injection**: Context is prepended to the user's prompt
5. **Execution**: Freebuff agent sees the context and uses it to inform its approach

## What Gets Injected

The AOS context includes:
- **Task classification** (category, difficulty, domains)
- **Recommended role** (e.g., backend-architect, security-engineer)
- **Relevant memories** (past decisions and patterns)
- **Safety warnings** (destructive actions, sensitive data)
- **Execution instructions** (role-based guidance)

## Comparison with MCP Approach

| | MCP (old) | Hook (Option C) |
|--|-----------|-----------------|
| **Trigger** | Agent must call tool | Automatic on every prompt |
| **Reliability** | Agent may forget | 100% guaranteed |
| **Latency** | Extra tool call | No extra call |
| **Agent awareness** | Agent knows about AOS | Agent unaware, behavior guided |
| **Pattern** | Agent opts in | System intercepts |

## Files

| File | Purpose |
|------|---------|
| `aos_bootstrap.py` | Python backend — calls AOS adapter, formats context |
| `hooks/prompt_submit.sh` | Bash hook — receives prompt, calls bootstrap, prepends context |
| `settings.json` | Freebuff hook configuration |
| `install.sh` | Installation script |

## Uninstall

Remove the `UserPromptSubmit` hook entry from your Freebuff `settings.json`:

```bash
# Global
~/.freebuff/settings.json

# Project-local
.freebuff/settings.json
```

Delete the hook entry from the `hooks.UserPromptSubmit` array.
