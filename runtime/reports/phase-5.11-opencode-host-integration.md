# Phase 5.11 — OpenCode Host Integration & AOS V1 Freeze

> **Date**: 2026-08-31
> **Status**: COMPLETE
> **Decision**: AOS V1 FREEZE — YES

---

## 1. OpenCode Host Audit

### Native Integration Points Discovered

| Feature | Status | Usage |
|---------|--------|-------|
| AGENTS.md | ✅ Native | Project-level instructions (first-match-wins) |
| CLAUDE.md | ✅ Native | Fallback instruction file (Claude Code compat) |
| Plugins | ✅ Native | JavaScript/TypeScript hooks (session, tool, message events) |
| MCP Servers | ✅ Native | Already configured (playwright, context7, github) |
| Commands | ✅ Native | Custom slash commands in `~/.config/opencode/command/` |
| opencode.jsonc | ✅ Native | Global config (MCP, plugins) |

### Integration Decision

**Chose: AGENTS.md** — the most native, minimal-invasion approach.

- OpenCode reads `AGENTS.md` from project root automatically
- No OpenCode modification required
- No plugin development required
- Standard OpenCode feature, zero coupling to AOS internals

---

## 2. Integration Design

```text
OpenCode (Host)
  ↓ reads AGENTS.md project instructions
  ↓ user requests complex task
  ↓ invokes: aos run "task" or python3 opencode_adapter.py "task"
AOS Host Adapter (translation layer)
  ↓ translates host format → AOS format
  ↓ invokes loop_controller
Agent OS Pipeline
  ↓ Router → Memory → Orchestrator → Runtime
  ↓ returns result
OpenCode (receives result)
```

### Key Principle

```
Host ≠ Agent OS
Runtime ≠ Agent OS
Model ≠ Agent OS
```

Host provides: task + working directory
AOS provides: routing + memory + orchestration + trace
Runtime provides: execution

---

## 3. Host Adapter

### Files Created

| File | Purpose |
|------|---------|
| `~/.agents/runtime/host-integration-contract.yaml` | Defines host ↔ AOS boundary contract |
| `~/.agents/runtime/hosts/opencode/opencode_adapter.py` | Minimal translation layer |
| `<project>/AGENTS.md` | OpenCode-native project instructions |

### Adapter Design

- **Input**: Task text + options (memory, model, provider, cwd)
- **Output**: AOS pipeline result (status, trace, tokens, latency)
- **No duplication**: Does NOT re-implement Router, Memory, or Orchestrator
- **Dynamic**: All config resolved from environment, never hardcoded

---

## 4. Provider Boundary

| Check | Result |
|-------|--------|
| Hardcoded providers in AOS core | ❌ None |
| `DEFAULT_PROVIDER` source | `os.environ.get("AOS_RUNTIME_PROVIDER", "opencode")` |
| Provider dispatch | Dynamic via `PROVIDER_DISPATCH` dict |
| New providers | Add to dispatch table + runtime-contract.yaml |

**Verdict**: PASS — Provider boundary intact.

---

## 5. Model Boundary

| Check | Result |
|-------|--------|
| Hardcoded models in AOS core | ❌ None |
| `DEFAULT_MODEL` source | `os.environ.get("AOS_RUNTIME_MODEL", "")` |
| Model in trace | Recorded from runtime result, not hardcoded |
| "mimo-v2.5-free" references | 1 occurrence — CLI help example string only |

**Verdict**: PASS — Model boundary intact.

---

## 6. Agent Boundary

| Check | Result |
|-------|--------|
| Hardcoded agent implementations | ❌ None |
| Role names in routing rules | ✅ Expected — routing matrix maps patterns → role strings |
| Agent code imports in AOS core | ❌ None |
| Role registry | `skills/meta/role-registry.md` (external, not imported) |

**Verdict**: PASS — Agent boundary intact.

---

## 7. Real Host Test

### Test Task

```
只读取当前项目的 pom.xml，告诉我 Java 版本。禁止修改任何文件。
```

### Pipeline Execution

| Stage | Status | Details |
|-------|--------|---------|
| Host Adapter | ✅ PASS | Task translated, AOS invoked |
| Router | ✅ PASS | Classified: Backend → backend-architect |
| Memory | ✅ PASS | 5 memories retrieved, 0 hypotheses |
| Orchestrator | ✅ PASS | Single-agent mode (correct for read-only task) |
| Runtime | ✅ PASS | OpenCode CLI, real session `ses_fa9b60014ffecBcTlSsrv0yfTf` |
| Trace | ✅ PASS | Full provenance recorded |
| Reconciler | ✅ PASS | CONSISTENT |

### Result

```
Java 版本: 21
Provider: opencode
Tokens: 25,939
Latency: 31,086ms
Status: success
```

### Chain Verified

```
OpenCode → AOS Host Adapter → Router → Memory → Orchestrator → OpenCode Runtime → Result
```

---

## 8. Trace

| Field | Value |
|-------|-------|
| Execution ID | EXEC-1788154083 |
| Trace ID | TRACE-EXEC-1788154083-8f127e7bb761 |
| Session ID | ses_fa9b60014ffecBcTlSsrv0yfTf |
| Provider | opencode |
| Model | (resolved by policy) |
| Status | success |
| Evidence Level | Level 2 — Runtime Validated |

---

## 9. Project Safety

| Check | Before | After | Delta |
|-------|--------|-------|-------|
| Modified tracked files | 32 | 32 | 0 |
| New untracked files | 2 | 3 | +1 (AGENTS.md) |
| AOS-induced changes | — | 0 | NO |

**Verdict**: PASS — No project files modified by AOS pipeline. `AGENTS.md` is the expected integration artifact.

---

## 10. AOS V1 Freeze Decision

### Freeze Criteria Checklist

| Criterion | Status |
|-----------|--------|
| Runtime Neutrality | ✅ PASS |
| Model Neutrality | ✅ PASS |
| Agent Neutrality | ✅ PASS |
| Provider Isolation | ✅ PASS |
| OpenCode Host | ✅ PASS |
| Router | ✅ PASS |
| Memory | ✅ PASS |
| Orchestrator | ✅ PASS |
| Trace | ✅ PASS |
| Telemetry | ✅ PASS |
| Feedback | ✅ PASS |
| Reconciliation | ✅ PASS |
| Project Safety | ✅ PASS |

### Decision

```
AOS V1 FREEZE: YES
```

### Freeze Rule

After V1 Freeze, modifications ONLY allowed for:

- Real project bugs
- Real Runtime bugs
- Real Memory failures
- Real Router failures
- Real Agent selection failures

Otherwise: AOS V1 stays unchanged.

---

## 11. Final Output

```
OPENCODE_HOST:        PASS
AOS_INTEGRATION:      PASS
RUNTIME_BOUNDARY:     PASS
MODEL_BOUNDARY:       PASS
AGENT_BOUNDARY:       PASS
ROUTER:               PASS
MEMORY:               PASS
ORCHESTRATOR:         PASS
TRACE:                PASS
PROJECT_MODIFIED:     NO
AOS_V1_FREEZE:        YES
NEXT:                 REAL_PROJECT_DEVELOPMENT
```
