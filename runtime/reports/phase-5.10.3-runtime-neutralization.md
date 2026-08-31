# Phase 5.10.3 — Runtime Neutralization Report

**Date**: 2026-08-31  
**Engineer**: Agent OS Architecture Engineer  
**Status**: COMPLETE

---

## 1. Current Binding Audit

### Pre-fix State

Before this phase, the following hardcoded bindings were found:

| File | Binding | Type | Status |
|------|---------|------|--------|
| `runtime_adapter.py` | `DEFAULT_MODEL = "opencode/mimo-v2.5-free"` | hardcoded model | **FIXED** |
| `runtime_adapter.py` | `invoke_opencode()` — hardcoded function | hardcoded provider | **FIXED** |
| `runtime_adapter.py` | `build_trace` `"backend": "opencode"` | hardcoded provider in trace | **FIXED** |
| `runtime_adapter.py` | `build_trace` fallback agent `"backend-architect"` | hardcoded agent | **FIXED** |
| `runtime_adapter.py` | `build_trace` `cli_command` — hardcoded "opencode run" | hardcoded provider | **FIXED** |
| `loop_controller.py` | `DEFAULT_MODEL = "opencode/mimo-v2.5-free"` | hardcoded model | **FIXED** |
| `loop_controller.py` | `init_loop_state` runtime.provider = "opencode" | hardcoded provider | **FIXED** |
| `loop_controller.py` | `run_loop` signature — no provider param | hardcoded provider | **FIXED** |
| `aos` | `DEFAULT_MODEL = "opencode/mimo-v2.5-free"` | hardcoded model | **FIXED** |
| `aos` | `OPENCODE_BIN = "opencode"` + validate_environment checks | hardcoded binary | **FIXED** |
| `aos` | `cmd_run` — no --provider flag | missing CLI param | **FIXED** |
| `execution-contract.yaml` | `model: "opencode/ling-3.0-flash-fin-free"` | hardcoded model | **FIXED** |

### Post-fix Classification

All remaining references to `opencode` or `mimo-v2.5-free` in core files:

| File | Line | Reference | Classification |
|------|------|-----------|----------------|
| `aos` | 33 | `DEFAULT_PROVIDER = os.environ.get("AOS_RUNTIME_PROVIDER", "opencode")` | **allowed** — env-overridable configuration |
| `aos` | 12,210,211 | Examples in docstring/epilog | **allowed** — configuration/examples |
| `runtime_adapter.py` | 32 | `DEFAULT_PROVIDER = os.environ.get(...)` | **allowed** — configuration |
| `runtime_adapter.py` | 129 | `_invoke_opencode_provider()` | **allowed** — runtime implementation |
| `runtime_adapter.py` | 250-253 | `PROVIDER_DISPATCH` dict | **allowed** — provider dispatch table |
| `runtime_adapter.py` | 566 | CLI usage example | **allowed** — configuration/examples |
| `loop_controller.py` | 52 | `DEFAULT_PROVIDER = os.environ.get(...)` | **allowed** — configuration |
| `loop_controller.py` | 184 | `run_loop(provider="opencode")` | **allowed** — overridable default param |
| `runtime-contract.yaml` | 16-31 | `opencode` provider definition | **allowed** — provider definition |
| `retrieval_adapter.py` | 53 | `"backend-architect"` role regex | **allowed** — role-registry configuration |

**Verdict**: Zero hardcoded architecture dependencies. All remaining references are either:
- Environment-overridable configuration defaults
- Provider implementation code (correctly scoped)
- Examples/documentation
- Role registry definitions (not agent bindings)

---

## 2. Runtime Contract

Created: `/home/shade/.agents/runtime/runtime-contract.yaml`

Defines:
- **runtime.provider**: Provider name (opencode, codex, ...)
- **runtime.executable**: Path to CLI binary
- **runtime.command**: Subcommand (e.g., "run")
- **runtime.model**: Provider-specific model identifier
- **runtime.capabilities**: Capability flags (session_tracking, token_tracking, etc.)
- **runtime.timeout**: Max execution time (300s default)
- **runtime.environment**: Env vars passed to provider

**Provider definitions**:
- `opencode`: executable="opencode", command="run", model_format="provider/model-id", status="supported"
- `codex`: executable="codex", command="run", model_format="provider/model-id", status="contract_only"

**Host integration contract**:
```yaml
host:
  type: ""              # cli | plugin | api
  runtime: ""           # provider name
  session: ""           # session identifier
  task: ""              # task description
  working_directory: "" # project directory
```

**Model selection**: Resolved via `AOS_RUNTIME_MODEL` env → CLI `--model` flag → provider default

---

## 3. Provider Abstraction

### Architecture

```
Agent OS
  ↓
Runtime Adapter (runtime_adapter.py)
  ↓
invoke_runtime(provider, prompt, model)
  ↓
PROVIDER_DISPATCH = {
    "opencode": _invoke_opencode_provider,
    "codex":    _invoke_codex_provider,
}
  ↓
Provider CLI
```

### Provider Functions

| Function | Purpose | Status |
|----------|---------|--------|
| `_invoke_opencode_provider()` | Real OpenCode CLI invocation | **implemented** |
| `_invoke_codex_provider()` | Contract-only stub | **contract only** |
| `invoke_runtime(provider, ...)` | Dispatch to correct provider | **implemented** |

### Key Design Decisions

1. Provider dispatch is a dict — new providers require only: a new `_invoke_*` function + dict entry
2. Each provider returns a standardized result dict with `status`, `session_id`, `tokens`, `response_text`, etc.
3. Agent OS core never calls `opencode` directly — always through `invoke_runtime()`

---

## 4. Model Selection

### Before

```python
# loop_controller.py
DEFAULT_MODEL = "opencode/mimo-v2.5-free"  # hardcoded invariant

# runtime_adapter.py
DEFAULT_MODEL = "opencode/mimo-v2.5-free"  # hardcoded invariant
```

### After

```python
# loop_controller.py
DEFAULT_MODEL = os.environ.get("AOS_RUNTIME_MODEL", "")  # env-driven

# runtime_adapter.py
DEFAULT_MODEL = os.environ.get("AOS_RUNTIME_MODEL", "")  # env-driven

# aos CLI
aos run "<task>" --model <model>   # CLI override
# or
AOS_RUNTIME_MODEL=opencode/mimo-v2.5-free aos run "<task>"  # env override
```

### Resolution Chain

```
CLI --model flag
  ↓ (if not set)
AOS_RUNTIME_MODEL env var
  ↓ (if not set)
provider default (empty string = provider decides)
```

---

## 5. Agent Decoupling

### Before

```python
# runtime_adapter.py build_trace fallback
lead_agent = role or "backend-architect"  # hardcoded fallback
```

### After

```python
# runtime_adapter.py
lead_agent = roles[0] if roles else f"{category}-engineer"  # derived from classification
```

Agent is now derived from:
1. `role-registry` → role matching
2. `router decision` → classification → lead_agent
3. `team formation` → orchestrator logic

No fixed lead agent, no fixed support agent, no fixed model.

---

## 6. OpenCode Adapter

### Before

```
Agent OS
  ↓
  directly executes opencode
```

### After

```
Agent OS
  ↓
  runtime_adapter.invoke_runtime(provider="opencode", ...)
  ↓
  PROVIDER_DISPATCH["opencode"] → _invoke_opencode_provider()
  ↓
  subprocess.run(["opencode", "run", ...])
```

OpenCode remains the current real runtime, but it is now accessed through the provider abstraction layer. The core Agent OS code has no special knowledge of OpenCode beyond what's in the provider dispatch table.

---

## 7. Codex Compatibility

**Status**: CONTRACT ONLY — no Codex installation, no Codex calls.

Design elements for Codex compatibility:
- `runtime-contract.yaml` defines `codex` provider with `executable: "codex"`, `command: "run"`
- `_invoke_codex_provider()` stub exists in the dispatch table
- Model is `host supplied` — no hardcoded fallback
- Contract is ready for future implementation

---

## 8. Regression Tests

### Test Execution

```bash
cd /home/shade/Public/test
aos run "只读取 pom.xml，告诉我 Java 版本，不修改任何文件" \
  --provider opencode \
  --model opencode/mimo-v2.5-free
```

### Results

| Component | Status | Detail |
|-----------|--------|--------|
| Router | PASS | Correctly classified as backend task |
| Memory | PASS | Retrieved 6 candidates, validated 0 (below threshold) |
| Orchestrator | PASS | Single-agent mode, anti-pattern guard active |
| Runtime | PASS | opencode CLI invoked, session recorded |
| Collector | PASS | 6 candidates generated |
| Validator | PASS | All rejected (quality below threshold) |
| Promoter | PASS | 0 promoted |
| Reconciler | PASS | CONSISTENT |
| Feedback | PASS | Pipeline complete |
| Trace | PASS | YAML written with provider/model |

### Trace Verification

```yaml
provider: opencode
model: opencode/mimo-v2.5-free
status: success
session_id: ses_fa9c325bbffekcPSHRa3Ubq5op
tokens: 25457
```

---

## 9. Project Safety

### Before Test

```
git status --short: 33 modified/deleted/untracked files (pre-existing)
```

### After Test

```
git status --short: 33 modified/deleted/untracked files (identical)
```

**PROJECT_MODIFIED = NO** — The test did not modify any project files.

---

## 10. Final Verdict

```
RUNTIME_NEUTRALIZATION:
PASS

RUNTIME_ABSTRACTION:
PASS

MODEL_DECOUPLED:
YES

AGENT_DECOUPLED:
YES

OPENCODE:
PROVIDER

CODEX:
COMPATIBLE

AOS_CORE:
RUNTIME_NEUTRAL

PROJECT_MODIFIED:
NO

NEXT:
VERIFY
```

### Summary of Changes

| File | Change | Lines |
|------|--------|-------|
| `runtime/runtime-contract.yaml` | NEW — runtime contract definition | 135 |
| `runtime/loop-controller/runtime_adapter.py` | Refactored — provider abstraction, dispatch, dynamic provider | 591 |
| `runtime/loop-controller/loop_controller.py` | Updated — provider param, env-based defaults | 530+ |
| `runtime/loop-controller/execution-contract.yaml` | Updated — removed hardcoded model, added provider | ~100 |
| `bin/aos` | Updated — --provider flag, removed OPENCODE_BIN, provider-agnostic | ~270 |

### Capabilities Preserved

All existing capabilities verified intact:
- [x] Router (classification-based)
- [x] Memory (retrieval + hypothesis separation)
- [x] Orchestrator (single/multi-agent, anti-pattern)
- [x] Retrieval (similarity + rule matching)
- [x] Feedback (candidate generation)
- [x] Promotion (validation + promotion)
- [x] Trace (YAML extraction)
- [x] Telemetry (token count, latency, cost)
- [x] Entry Evidence (AOS_ENTRY_METADATA)