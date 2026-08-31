# Phase 5.9.2.1 — Runtime Backend Diagnostic Report

**Date**: 2026-08-31
**Phase**: 5.9.2.1
**Target**: PROJ-001-T001 Runtime Debugging

---

## 1. Environment

```yaml
os: linux (x86-64)
shell: zsh
opencode_binary: /home/shade/.opencode/bin/opencode (ELF 64-bit native)
opencode_version: 1.18.25
```

## 2. CLI

```yaml
cli:
  executable: /home/shade/.opencode/bin/opencode
  version: 1.18.25
  available_commands: [run, auth, providers, models]
```

## 3. Providers

```yaml
providers:
  credentials_file: ~/.local/share/opencode/auth.json → NOT FOUND
  configured_credentials: 0
  environment_variables: 1 (GITHUB_TOKEN)
  github_copilot: present (but auth failed)
  opencode_free_models: present (no auth required)
```

## 4. Free Models

| Model | Available | Status |
|-------|-----------|--------|
| opencode/ling-3.0-flash-fin-free | listed | timeout |
| opencode/big-pickle | listed | timeout |
| opencode/nemotron-3.5-lightning-free | listed | timeout |
| opencode/mimo-v2.5-free | listed | WORKING |
| opencode/muse-spark-1.2-contributor-free | listed | region blocked |
| opencode/nemotron-3-ultra-free | listed | not tested |

## 5. Smoke Tests

| Model | Prompt | Timeout | Status | Latency |
|-------|--------|---------|--------|---------|
| ling-3.0 | "say RUNTIME_OK" | 30s | timeout (124) | 30000ms |
| big-pickle | "say RUNTIME_OK" | 30s | timeout (124) | 30000ms |
| nemotron-3.5 | "say RUNTIME_OK" | 30s | timeout (124) | 30000ms |
| mimo-v2.5 | "say RUNTIME_OK" | 30s | SUCCESS | 14200ms |
| muse-spark | "say RUNTIME_OK" | 30s | blocked | 8900ms |

## 6. Project Read Tests

| Model | Task | Timeout | Status | Latency | Output |
|-------|------|---------|--------|---------|--------|
| mimo-v2.5 | Read pom.xml → Java version | 60s | SUCCESS | 28400ms | Java 21 |

## 7. Java File Tests

| Model | Task | Timeout | Status | Latency | Output |
|-------|------|---------|--------|---------|--------|
| mimo-v2.5 | Read RagService.java → summarize | 120s | SUCCESS | 26900ms | retrieval flow summary |

## 8. T001 Analysis Test

| Model | Task | Timeout | Status | Latency | Output |
|-------|------|---------|--------|---------|--------|
| mimo-v2.5 | Analyze RAG retrieval, no modify | 120s | SUCCESS | 97100ms | comprehensive analysis |

**Analysis output highlights**:
- P1: Full loading of all chunks into memory (line 124-128)
- P2: Vector stored as JSON string in MySQL
- R1: No hybrid retrieval (BM25 + vector)
- R2: Fixed chunk strategy (500/50)
- A1: No re-ranking (cross-encoder)
- Proposed: pgvector, hybrid retrieval, re-ranking

## 9. Adapter Audit

```yaml
file: runtime/loop-controller/runtime_adapter.py
adapter_bug: false
findings:
  - subprocess: correct (subprocess.run with capture_output=True, text=True)
  - timeout: configurable (TIMEOUT_SECONDS, was 120s, now 300s)
  - stdout: correctly captured
  - stderr: correctly captured
  - exit_code: correctly checked
  - JSON parsing: correct (text → sessionID, step_finish → tokens)
  - session extraction: correct (from part.sessionID)
  - --auto flag: used by adapter, but NOT the cause of timeout
  - --format json: works with mimo
notes: |
  The adapter logic is correct. The timeout is at the provider level,
  not the adapter level. The adapter correctly handles timeout and
  error cases with proper fallback to empty session/tokens.
```

## 10. Timeout Classification

| Type | Models | Evidence |
|------|--------|----------|
| provider_timeout | ling, big-pickle, nemotron | CLI hangs, no stdout, no stderr, exit 124. No error message from provider. |
| provider_region_blocked | muse-spark | "This model is not available in your country" |
| provider_auth_failed | github-copilot | "Unauthorized: AuthenticateToken authentication failed" |
| adapter_timeout | NONE | Adapter logic verified correct |
| network_timeout | NONE | mimo works, network is functional |
| workspace_timeout | NONE | mimo can read files from workspace |

**Root cause**: ling-3.0, big-pickle, and nemotron-3.5 providers are non-responsive. The CLI sends a request but never receives a response. No error is returned, just silence until timeout.

## 11. Git Integrity

```yaml
before: clean (main, 56788e5)
after: clean (main, 56788e5)
changes: 0
```

**No project files were modified.**

## 12. Diagnostic Matrix

See: [phase-5.9.2.1-runtime-diagnostic-matrix.yaml](file:///home/shade/.agents/runtime/reports/phase-5.9.2.1-runtime-diagnostic-matrix.yaml)

## 13. Root Cause

```yaml
root_cause: |
  3 of 5 free OpenCode models (ling-3.0, big-pickle, nemotron-3.5)
  are non-responsive at the provider level. The CLI hangs without
  producing any output, error, or session.

  This is NOT:
  - An adapter bug
  - A network issue (mimo works)
  - A workspace issue (mimo can read project files)
  - A prompt complexity issue (even "say RUNTIME_OK" times out)

  This IS:
  - A provider-level issue: the API endpoints for these models
    are not responding to requests from this environment/region.

working_model: opencode/mimo-v2.5-free
```

## 14. Recommended Runtime Fix

```yaml
option_1_recommended:
  description: |
    Switch the default model in runtime_adapter.py from
    ling-3.0-flash-fin-free to mimo-v2.5-free.
  changes:
    - file: runtime/loop-controller/runtime_adapter.py
    - line: DEFAULT_MODEL = "opencode/mimo-v2.5-free"
  risk: low
  impact: |
    mimo-v2.5-free works with --auto, --format json, can read
    project files, and can analyze code. Latency is acceptable
    (15-97s depending on complexity).

option_2:
  description: |
    Add --pure flag to the opencode command to bypass plugins.
    This may help with other models but did not fix the timeout
    for ling/big-pickle/nemotron.
  risk: low
  impact: unknown

option_3:
  description: |
    Use GitHub Copilot models with a valid GITHUB_TOKEN.
  risk: medium (requires valid token)
  impact: would unlock all Claude/GPT models
```

## 15. Final Status

```yaml
RUNTIME_BACKEND_STATUS: DEGRADED

WORKSPACE_READ: PASS
  model: mimo-v2.5-free

AGENT_ANALYSIS: PASS
  model: mimo-v2.5-free
  task: PROJ-001-T001 analysis

ROOT_CAUSE: |
  ling-3.0, big-pickle, nemotron-3.5 providers are non-responsive.
  mimo-v2.5-free is the only working free model.

ADAPTER_BUG: NO

NEXT_ACTION: |
  Switch default model to mimo-v2.5-free in runtime_adapter.py,
  then re-run PROJ-001-T001 with the working model.
```

---

Generated: 2026-08-31
Phase: 5.9.2.1
Report: runtime/reports/phase-5.9.2.1-runtime-diagnostic.md