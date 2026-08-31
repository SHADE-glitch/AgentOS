# Phase 6.0.1 — Host Integration Architecture Design

**Audit Type**: Architecture Design (Read-Only, No Implementation)  
**Design Date**: 2026-08-31T05:55:00+00:00  
**Trigger**: Phase 6.1 bypass confirmed — natural host integration = FAIL  
**Goal**: Design how OpenCode / Codex / Claude Code / Trae auto-enter AOS without explicit user invocation

---

## 1. Current Architecture

### 1.1 Current State

```
┌─────────┐
│  USER   │
└────┬────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  OpenCode (Host)                                 │
│                                                  │
│  AGENTS.md  ───→  "When task is complex,         │
│                    run `aos run \"task\"`"       │
│                                                  │
│  PROBLEM: Model may or may not follow            │
│           AGENTS.md instructions.                │
│           Phase 6.1 confirmed it did NOT.        │
└────────────┬────────────────────────────────────┘
             │
     ┌───────┴───────┐
     │               │
     ▼               ▼
┌─────────┐   ┌──────────────┐
│ Direct  │   │  Manual      │
│ Execute │   │  aos run     │
│ (BYPASS)│   │  (WORKS)     │
└─────────┘   └──────┬───────┘
                     │
                     ▼
            ┌─────────────────┐
            │  Agent OS       │
            │  (Loop Ctrl)    │
            └─────────────────┘
```

### 1.2 What Works

| Component | Status | Detail |
|-----------|--------|--------|
| `aos run "task"` | WORKS | Manual CLI entry → full pipeline |
| `opencode_adapter.py` | WORKS | Host adapter translates OpenCode → AOS |
| Loop Controller | WORKS | Retrieval → Router → Orchestrator → Runtime |
| Trace | WORKS | Full execution provenance |
| Feedback | WORKS | Candidate collection + validation |
| Agent Routing | WORKS | Dynamic role selection via ROLE_RULES |
| Memory Retrieval | WORKS | Pattern + effectiveness + failure retrieval |

### 1.3 What Doesn't Work

| Component | Status | Detail |
|-----------|--------|--------|
| **Auto-bootstrap** | FAIL | Phase 6.1 confirmed: task bypassed AOS entirely |
| AGENTS.md instructions | UNRELIABLE | Model may or may not follow project instructions |
| Host interception | MISSING | No hook/plugin/mechanism to intercept tasks |

### 1.4 Root Cause

The current integration relies on **model compliance** with AGENTS.md instructions. This is fundamentally unreliable because:

1. **AGENTS.md is a prompt, not a mechanism** — it depends on the model reading and following instructions
2. **No automated interception** — no hook, plugin, or middleware that fires before task execution
3. **Manual-only entry** — `aos run` is the only guaranteed path to AOS
4. **No host-native integration** — OpenCode has no native awareness of AOS

---

## 2. Host Capability Analysis

### 2.1 Host Comparison Matrix

| Capability | OpenCode | Codex | Claude Code | Trae |
|------------|----------|-------|-------------|------|
| **Plugin System** | JS/TS plugins | Python SDK | Plugin system | Plugin API |
| **Hook Events** | 15+ events | 4 events | 5 events | 6 events |
| **Project Config** | `opencode.json` | `.codex/` | `CLAUDE.md` | `hooks.json` |
| **Global Config** | `~/.config/opencode/` | `~/.codex/` | `~/.claude/` | `settings.json` |
| **AGENTS.md** | Yes | No | `CLAUDE.md` | No |
| **MCP** | Yes | No | Yes | No |
| **SDK** | JS/TS SDK | Python SDK | Plugin SDK | Plugin API |
| **SessionStart** | `session.created` | `Stop` hook | `SessionStart` | `SessionStart` |
| **UserPrompt** | `tui.prompt.append` | `UserPromptSubmit` | `UserPromptSubmit` | `UserPromptSubmit` |
| **Tool Intercept** | `tool.execute.before` | `PreToolUse` | `PreToolUse` | `PreToolUse` |
| **Auto-Bootstrap** | Plugin | Hook script | Hook/Plugin | Hook |

### 2.2 Key Events for Auto-Bootstrap

| Host | Best Bootstrap Event | Alternative |
|------|---------------------|-------------|
| **OpenCode** | `session.created` | `tool.execute.before` (first call) |
| **Codex** | `UserPromptSubmit` | `Stop` |
| **Claude Code** | `SessionStart` | `UserPromptSubmit` |
| **Trae** | `UserPromptSubmit` | `SessionStart` |

---

## 3. AUTO_BOOTSTRAP Location Evaluation

### 3.1 Option Matrix

| Option | Reliability | Transparency | Maintainability | Host Portability | Security | Model Dependency | Invasive |
|--------|-------------|--------------|-----------------|------------------|----------|------------------|----------|
| **Host Plugin** | HIGH | HIGH | HIGH | HIGH | HIGH | NONE | MINIMAL |
| **Host Hook** | HIGH | HIGH | MEDIUM | HIGH | MEDIUM | NONE | MINIMAL |
| **Shell Wrapper** | MEDIUM | LOW | LOW | LOW | LOW | NONE | NO |
| **MCP** | MEDIUM | MEDIUM | MEDIUM | HIGH | HIGH | NONE | MINIMAL |
| **CLI Middleware** | MEDIUM | LOW | LOW | LOW | LOW | NONE | YES |
| **Project Instruction** | LOW | HIGH | HIGH | HIGH | HIGH | YES | NO |
| **Global Instruction** | LOW | HIGH | HIGH | HIGH | HIGH | YES | NO |

### 3.2 Verdict

**Winning strategy**: Host Plugin (primary) + Host Hook (fallback for hosts without plugin system)

**Why not AGENTS.md**: Phase 6.1 proved that project instructions are unreliable. The model may optimize them away, ignore them, or the host may not even read them in certain execution modes.

**Why not shell wrapper**: Fragile, bypassable, opaque to the user. The user expects to run `opencode`, not `aos-opencode`.

**Why not MCP**: MCP is for tool integration, not for task interception. It runs after the model decides to call a tool, which is too late.

---

## 4. Recommended Architecture

### 4.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Agent Hosts                                │
│                                                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐      │
│  │ OpenCode │   │  Codex   │   │ Claude   │   │   Trae   │      │
│  │          │   │          │   │  Code    │   │          │      │
│  │ Plugin   │   │ Hook     │   │ Plugin   │   │ Hook     │      │
│  │ (.ts)    │   │ (.sh)    │   │ (.sh)    │   │ (.json)  │      │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘      │
│       │              │              │              │              │
└───────┼──────────────┼──────────────┼──────────────┼──────────────┘
        │              │              │              │
        └──────────────┼──────────────┼──────────────┘
                       │              │
                       ▼              ▼
              ┌────────────────────────────────┐
              │   AOS Bootstrap Protocol       │
              │   (Common JSON Interface)      │
              │                                │
              │   stdin:  {task, cwd, ...}     │
              │   stdout: {routed, result,...} │
              └──────────────┬─────────────────┘
                             │
                             ▼
              ┌────────────────────────────────┐
              │       Agent OS Pipeline        │
              │                                │
              │  Router → Memory → Orchestrator│
              │       → Runtime → Trace        │
              └────────────────────────────────┘
```

### 4.2 Bootstrap Protocol (Common JSON Interface)

All host adapters communicate with AOS through a single, host-neutral protocol:

```json
// INPUT (stdin to aos-bootstrap)
{
  "task": "user's natural language task",
  "working_directory": "/path/to/project",
  "host": "opencode",
  "session_id": "host-session-id",
  "metadata": {
    "entry_type": "host_bootstrap",
    "host_event": "session.created"
  }
}

// OUTPUT (stdout from aos-bootstrap)
{
  "routed": true,
  "execution_id": "EXEC-xxxxxxxxxx",
  "trace_id": "TRACE-...",
  "lead_agent": "backend-architect",
  "support_agents": ["security-engineer"],
  "memories_retrieved": 5,
  "result": "...",
  "provider": "opencode",
  "model": "",
  "tokens": {"input": 1000, "output": 500},
  "latency_ms": 15000
}
```

### 4.3 Neutrality Guarantees

| Dimension | How Enforced |
|-----------|-------------|
| **Host Neutral** | Bootstrap protocol is JSON-in/JSON-out; no host-specific logic in AOS core |
| **Runtime Neutral** | Provider resolved by policy (CLI > env > host > default); no hardcoded provider |
| **Model Neutral** | Model resolved by policy (CLI > env > host > provider default); no hardcoded model |
| **Agent Neutral** | Agent roles are strings from ROLE_RULES; no agent class instantiation in core |
| **Project Neutral** | Working directory passed from host; no fixed project path |

---

## 5. Per-Host Integration Design

### 5.1 OpenCode Integration

**Mechanism**: Native Plugin (JS/TS)

**Event**: `session.created` — fires when OpenCode creates a session, before first user interaction

**Plugin location**: `.opencode/plugins/aos-bootstrap.ts`

**Plugin structure**:

```typescript
// .opencode/plugins/aos-bootstrap.ts
import type { Plugin } from "@opencode-ai/plugin"

export const AOSBootstrap: Plugin = async ({ directory, $ }) => {
  return {
    event: async ({ event }) => {
      if (event.type !== "session.created") return

      // Check if AOS is available for this project
      const aosAvailable = await $`test -f ~/.agents/runtime/loop-controller/loop_controller.py && echo "yes" || echo "no"`.text()

      if (aosAvailable.trim() !== "yes") return

      // Inject AOS context into environment
      // This makes AOS available to the session without requiring explicit invocation
    },

    "shell.env": async (input, output) => {
      // Inject AOS environment variables into all shell executions
      output.env.AOS_ROOT = `${process.env.HOME}/.agents`
      output.env.AOS_ACTIVE = "1"
      output.env.AOS_PROJECT = input.cwd
    },

    "tui.prompt.append": async (input, output) => {
      // Optionally append AOS context to user prompts
      // This is a transparency mechanism, not the primary bootstrap
    }
  }
}
```

**Alternative**: Use `tool.execute.before` to intercept the first tool call and inject AOS routing.

**Configuration** (`opencode.json`):

```json
{
  "plugin": ["./.opencode/plugins/aos-bootstrap.ts"]
}
```

**Assessment**:

| Criterion | Assessment |
|-----------|-----------|
| Reliability | HIGH — `session.created` fires deterministically |
| Transparency | HIGH — plugin visible in `.opencode/plugins/` |
| Invasiveness | MINIMAL — uses documented plugin API |
| Model dependency | NONE — plugin fires before model interaction |

### 5.2 Codex Integration

**Mechanism**: Hook Script (Bash)

**Event**: `UserPromptSubmit` — fires when user submits a prompt, before agent processing

**Hook location**: `.codex/hooks/aos-bootstrap.sh`

**Hook structure**:

```bash
#!/usr/bin/env bash
# .codex/hooks/aos-bootstrap.sh
# Triggered by: UserPromptSubmit

INPUT=$(cat)
TASK=$(echo "$INPUT" | jq -r '.prompt // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Only intercept complex tasks (heuristic)
WORD_COUNT=$(echo "$TASK" | wc -w)
if [ "$WORD_COUNT" -lt 5 ]; then
  echo '{"continue": true}'
  exit 0
fi

# Check if AOS is available
AOS_CONTROLLER="$HOME/.agents/runtime/loop-controller/loop_controller.py"
if [ ! -f "$AOS_CONTROLLER" ]; then
  echo '{"continue": true}'
  exit 0
fi

# Route through AOS
RESULT=$(python3 "$AOS_CONTROLLER" \
  "CODEX-$(uuidgen | cut -c1-6)" \
  "$TASK" \
  "enabled" \
  "" \
  "opencode" \
  2>&1)

# Append AOS context to the prompt
echo "{\"continue\": true, \"appendContext\": \"[AOS: Routed through Agent OS. Memories retrieved. Lead agent assigned.]\"}"
```

**Assessment**:

| Criterion | Assessment |
|-----------|-----------|
| Reliability | HIGH — `UserPromptSubmit` fires deterministically |
| Transparency | HIGH — hook visible in `.codex/hooks/` |
| Invasiveness | MINIMAL — uses documented hook API |
| Model dependency | NONE — hook fires before model processing |
| Status | DESIGN_ONLY — not implemented |

### 5.3 Claude Code Integration

**Mechanism**: Hook Script (Bash) via Plugin System

**Event**: `SessionStart` — fires when a session starts, before first user interaction

**Hook location**: `.claude/hooks/aos-bootstrap.sh`

**Hook structure**:

```bash
#!/usr/bin/env bash
# .claude/hooks/aos-bootstrap.sh
# Triggered by: SessionStart

INPUT=$(cat)

# Check if AOS is available for this project
AOS_CONTROLLER="$HOME/.agents/runtime/loop-controller/loop_controller.py"
if [ ! -f "$AOS_CONTROLLER" ]; then
  echo '{"continue": true}'
  exit 0
fi

# Inject AOS context
echo '{
  "continue": true,
  "appendContext": "Agent OS (AOS) is active for this project. 
AOS provides: automatic agent routing, memory retrieval of past decisions, 
and multi-agent orchestration for complex tasks. 
Your tasks will be automatically routed through AOS."
}'
```

**Alternative**: `UserPromptSubmit` hook for per-task interception

**Assessment**:

| Criterion | Assessment |
|-----------|-----------|
| Reliability | HIGH — `SessionStart` fires deterministically |
| Transparency | HIGH — hook visible in `.claude/hooks/` |
| Invasiveness | MINIMAL — uses documented hook API |
| Model dependency | NONE — hook fires before model processing |
| Status | DESIGN_ONLY — not implemented |

### 5.4 Trae Integration

**Mechanism**: Hook (JSON configuration)

**Event**: `UserPromptSubmit` — fires when user submits a query, before agent processing

**Hook location**: Project `.trae/hooks.json` or global `settings.json`

**Hook structure** (`hooks.json`):

```json
{
  "hooks": [
    {
      "event": "UserPromptSubmit",
      "command": "~/.agents/runtime/hosts/trae/trae-bootstrap.sh",
      "conditions": []
    }
  ]
}
```

**Bootstrap script** (`~/.agents/runtime/hosts/trae/trae-bootstrap.sh`):

```bash
#!/usr/bin/env bash
# Trae AOS Bootstrap Hook

INPUT=$(cat)
TASK=$(echo "$INPUT" | jq -r '.prompt // empty')

# Complexity heuristic: skip simple tasks
WORD_COUNT=$(echo "$TASK" | wc -w)
if [ "$WORD_COUNT" -lt 5 ]; then
  echo '{"continue": true}'
  exit 0
fi

AOS_CONTROLLER="$HOME/.agents/runtime/loop-controller/loop_controller.py"
if [ -f "$AOS_CONTROLLER" ]; then
  echo '{"continue": true, "appendContext": "[AOS active: intelligent routing + memory retrieval enabled]"}'
else
  echo '{"continue": true}'
fi
```

**Assessment**:

| Criterion | Assessment |
|-----------|-----------|
| Reliability | HIGH — `UserPromptSubmit` fires deterministically |
| Transparency | HIGH — hook visible in Trae settings |
| Invasiveness | MINIMAL — uses documented hook API |
| Model dependency | NONE — hook fires before model processing |
| Status | DESIGN_ONLY — not implemented |

---

## 6. Security Model

### 6.1 Threat Model

| Threat | Mitigation |
|--------|------------|
| Hook bypass (user disables plugin) | AOS is opt-in; bypass = no AOS, not a security failure |
| Malicious plugin replacement | Plugin files are in project/global config, user-controlled |
| AOS crash blocking host | Bootstrap is non-blocking; failure → passthrough |
| Sensitive task data in hook logs | Hook logs are local, user-readable only |
| Cross-host session leakage | Each host has independent bootstrap; no shared session state |

### 6.2 Bootstrap Safety Rules

```
1. Bootstrap NEVER blocks the host
   → On failure, always passthrough: {"continue": true}

2. Bootstrap NEVER modifies the task
   → Only appends context; original task text is preserved

3. Bootstrap NEVER stores user data
   → Only passes task to AOS; no external logging

4. Bootstrap NEVER requires network access
   → All operations are local

5. Bootstrap is ALWAYS opt-out
   → User can disable the plugin/hook at any time
```

---

## 7. Portability Model

### 7.1 Host Adapter Matrix

```
                    ┌──────────────────────────────────────┐
                    │     AOS Bootstrap Protocol (JSON)     │
                    │     ~/.agents/runtime/aos-bootstrap   │
                    └──────────────────┬───────────────────┘
                                       │
        ┌──────────────┬───────────────┼───────────────┬──────────────┐
        │              │               │               │              │
        ▼              ▼               ▼               ▼              ▼
   ┌─────────┐   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
   │OpenCode │   │  Codex  │    │ Claude  │    │  Trae   │    │ Future  │
   │ Plugin  │   │  Hook   │    │  Code   │    │  Hook   │    │  Host   │
   │  .ts    │   │  .sh    │    │  Hook   │    │  .json  │    │  ???    │
   └─────────┘   └─────────┘    └─────────┘    └─────────┘    └─────────┘
```

### 7.2 Adding a New Host

To add a new host, only two things are needed:

1. **A thin adapter** (plugin/hook/script) that:
   - Intercepts the host's task submission event
   - Translates host format → AOS Bootstrap Protocol JSON
   - Calls `aos-bootstrap`
   - Returns result to host

2. **No AOS core changes** — the bootstrap protocol is host-agnostic

---

## 8. Migration Strategy

### 8.1 Phased Rollout

| Phase | Action | Hosts | Risk |
|-------|--------|-------|------|
| **Phase 6.0.2** | Implement OpenCode Plugin | OpenCode | LOW (native API) |
| **Phase 6.0.3** | Implement `aos-bootstrap` common protocol | All | LOW (new component) |
| **Phase 6.0.4** | Validation: auto-bootstrap test | OpenCode | LOW |
| **Phase 6.0.5** | Implement Codex Hook | Codex | LOW (design only) |
| **Phase 6.0.6** | Implement Claude Code Hook | Claude Code | LOW (design only) |
| **Phase 6.0.7** | Implement Trae Hook | Trae | LOW (design only) |

### 8.2 Backward Compatibility

- `aos run` CLI remains available as manual entry
- `opencode_adapter.py` remains available
- AGENTS.md remains as documentation (not as bootstrap mechanism)
- Existing traces and loop states are unaffected

### 8.3 Opt-Out Mechanism

- User can delete `.opencode/plugins/aos-bootstrap.ts` to disable
- User can disable the hook in Trae settings
- No AOS core changes required to disable

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OpenCode plugin API changes | LOW | MEDIUM | Plugin uses stable public API; version-pin if needed |
| Bootstrap adds latency | MEDIUM | LOW | Async, non-blocking; < 100ms overhead |
| User confusion about AOS transparency | MEDIUM | LOW | Plugin appends `[AOS]` prefix to context; visible in logs |
| Hook execution permission denied | LOW | HIGH | Install script sets correct permissions |
| Multiple hosts active simultaneously | LOW | LOW | Each host has independent bootstrap; no cross-talk |

---

## 10. Acceptance Criteria

### 10.1 Auto-Bootstrap Verification

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | User types natural task in OpenCode | No mention of AOS, `aos run`, or "use Agent OS" |
| 2 | AOS pipeline activates automatically | New execution_id, trace_id, session_id generated |
| 3 | Router classifies task | Intent field in trace shows correct classification |
| 4 | Memory retrieval executes | Memory_retrieval in trace shows retrieved memories |
| 5 | Agent executes task | Trace shows agent_invocation with provider/model |
| 6 | Task result returned to user | User sees result in OpenCode |
| 7 | Full trace recorded | EXEC-*.yaml file exists with all pipeline stages |
| 8 | No duplicate execution | AOS runs once, not twice |
| 9 | Bootstrap failure does not block host | AOS crash → task executes normally |
| 10 | User can opt out | Delete plugin → no AOS activation |

---

## 11. Final Verdict

```
HOST_INTEGRATION:   DESIGN_READY

OPEN_CODE:          SUPPORTED
CODEX:              DESIGN_ONLY
CLAUDE_CODE:        DESIGN_ONLY
TRAE:               DESIGN_ONLY

MODEL_NEUTRAL:      YES
AGENT_NEUTRAL:      YES
RUNTIME_NEUTRAL:    YES

NEXT:               Implement OpenCode Plugin (Phase 6.0.2)
```

---

## 12. Key Design Decisions

### 12.1 Why Plugin, not AGENTS.md?

| | AGENTS.md (Current) | Plugin (Proposed) |
|---|---|---|
| Activation | Model-dependent | Deterministic |
| Reliability | Phase 6.1: FAILED | `session.created` always fires |
| Timing | After model reads file | Before first model interaction |
| Bypass risk | HIGH (model ignores) | LOW (only if user disables) |
| Audit trail | None | Plugin can log activation |

### 12.2 Why `session.created`, not `tool.execute.before`?

`session.created` fires once per session — before any user interaction. This is the earliest possible interception point. `tool.execute.before` fires on every tool call, which would add overhead and complexity.

### 12.3 Why Bootstrap Protocol, not per-host implementation?

A single, JSON-based bootstrap protocol ensures:
- AOS core never imports host-specific code
- New hosts can be added without AOS core changes
- The protocol is the contract; hosts are adapters
- Testing is simpler (one protocol, multiple adapters)

### 12.4 What About the Existing `opencode_adapter.py`?

The existing `opencode_adapter.py` becomes the **implementation** of the bootstrap protocol for OpenCode. The plugin calls `opencode_adapter.py` (or the loop controller directly) with the standardized JSON input.

---

## 13. Architecture Diagram (Complete)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HOST LAYER                                     │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │    OpenCode      │  │    Codex     │  │ Claude Code  │  │   Trae   │ │
│  │                  │  │              │  │              │  │          │ │
│  │ .opencode/       │  │ .codex/      │  │ .claude/     │  │ hooks.   │ │
│  │   plugins/       │  │   hooks/     │  │   hooks/     │  │ json     │ │
│  │   aos-bootstrap  │  │   aos-       │  │   aos-       │  │          │ │
│  │   .ts            │  │   bootstrap  │  │   bootstrap  │  │ trae-    │ │
│  │                  │  │   .sh        │  │   .sh        │  │ bootstrap│ │
│  │                  │  │              │  │              │  │ .sh      │ │
│  └────────┬─────────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘ │
│           │                   │                  │               │       │
└───────────┼───────────────────┼──────────────────┼───────────────┼───────┘
            │                   │                  │               │
            └───────────────────┼──────────────────┼───────────────┘
                                │                  │
                                ▼                  ▼
            ┌───────────────────────────────────────────────────┐
            │            HOST INTEGRATION LAYER                  │
            │                                                   │
            │  ┌─────────────────────────────────────────────┐  │
            │  │        AOS Bootstrap Protocol               │  │
            │  │        (JSON stdin → JSON stdout)           │  │
            │  │                                             │  │
            │  │  ~/.agents/runtime/aos-bootstrap            │  │
            │  │                                             │  │
            │  │  Responsibilities:                          │  │
            │  │  - Task complexity check                    │  │
            │  │  - AOS pipeline invocation                  │  │
            │  │  - Result passthrough                       │  │
            │  │  - Failure → continue (never block)         │  │
            │  └──────────────────┬──────────────────────────┘  │
            │                     │                              │
            └─────────────────────┼──────────────────────────────┘
                                  │
                                  ▼
            ┌───────────────────────────────────────────────────┐
            │                  AGENT OS LAYER                    │
            │                                                   │
            │  ┌─────────┐  ┌─────────┐  ┌─────────────────┐   │
            │  │ Router  │  │ Memory  │  │  Orchestrator   │   │
            │  │         │  │         │  │                 │   │
            │  │ Intent  │  │ Patterns│  │  Team Formation │   │
            │  │ → Agent │  │ Failures│  │  Role Assign    │   │
            │  └────┬────┘  └────┬────┘  └───────┬─────────┘   │
            │       │            │               │              │
            │       └────────────┼───────────────┘              │
            │                    │                              │
            │                    ▼                              │
            │  ┌─────────────────────────────────────────────┐  │
            │  │           Loop Controller                   │  │
            │  │                                             │  │
            │  │  Retrieval → Decision → Router →            │  │
            │  │  Orchestrator → Runtime → Trace →           │  │
            │  │  Feedback → Validation → Promotion          │  │
            │  └──────────────────┬──────────────────────────┘  │
            │                     │                              │
            └─────────────────────┼──────────────────────────────┘
                                  │
                                  ▼
            ┌───────────────────────────────────────────────────┐
            │               RUNTIME LAYER                        │
            │                                                   │
            │  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
            │  │ OpenCode │  │  Codex   │  │  Claude  │        │
            │  │  CLI     │  │  SDK     │  │  API     │        │
            │  └──────────┘  └──────────┘  └──────────┘        │
            │                                                   │
            │  Provider resolved by policy:                     │
            │  CLI > env > host > default                       │
            └───────────────────────────────────────────────────┘
```

---

## 14. Evidence References

| Evidence | Path |
|----------|------|
| Current Host Adapter | `/home/shade/.agents/runtime/hosts/opencode/opencode_adapter.py` |
| Host Integration Contract | `/home/shade/.agents/runtime/host-integration-contract.yaml` |
| Loop Controller | `/home/shade/.agents/runtime/loop-controller/loop_controller.py` |
| Runtime Adapter | `/home/shade/.agents/runtime/loop-controller/runtime_adapter.py` |
| Retrieval Adapter | `/home/shade/.agents/runtime/loop-controller/retrieval_adapter.py` |
| Phase 6.1 Audit (bypass evidence) | `/home/shade/.agents/runtime/reports/phase-6.1-independent-audit.md` |
| Phase 6.0 Audit | `/home/shade/.agents/runtime/reports/phase-6.0-natural-usage-audit.md` |
| Project AGENTS.md | `/home/shade/Public/test/AGENTS.md` |
| OpenCode Plugin Docs | https://opencode.ai/docs/zh-cn/plugins |
| Codex Hooks Docs | https://developers.openai.com/codex/hooks |
| Claude Code Plugins | https://www.anthropic.com/news/claude-code-plugins |
| Trae Hooks Docs | https://docs.trae.cn/ide_automate-actions-with-hooks |