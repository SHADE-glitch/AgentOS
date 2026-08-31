# Phase 5.10 — Agent OS Bootstrap & Entry-Point Audit

**Date**: 2026-08-31
**Phase**: 5.10
**Status**: COMPLETE
**Audit Type**: READ-ONLY

---

## 1. OpenCode Startup Path

```yaml
opencode:
  binary: /home/shade/.opencode/bin/opencode
  type: ELF binary (Go-compiled)
  path_resolved: /home/shade/.opencode/bin/opencode
  config_dir: /home/shade/.config/opencode/
  data_dir: /home/shade/.local/share/opencode/
  home_dir: /home/shade/.opencode/
```

### 1.1 OpenCode Configuration

File: `/home/shade/.config/opencode/opencode.jsonc`

```yaml
plugins:
  - github:JRedeker/opencode-morph-fast-apply
  - opencode-supermemory@latest
  - "@tarquinen/opencode-dcp@latest"
  - "@mohak34/opencode-notifier@latest"

mcp:
  - playwright (local)
  - context7 (remote)
  - github (local)

no_agent_os_plugin: true
no_agent_os_hook: true
no_agent_os_mcp: true
```

**Finding**: OpenCode has NO plugin, MCP, or hook that references Agent OS. The four plugins installed are: morph-fast-apply, supermemory, dcp, and notifier. None of them are Agent OS.

### 1.2 OpenCode Runtime Log

File: `/home/shade/.local/share/opencode/log/opencode.log`

Last activity (2026-08-31T03:56 UTC): `run=ac5a7796` was a direct OpenCode session working on `/home/shade/Public/test` with `mimo-v2.5-free` model. This session ran `mvn compile` commands directly — no Agent OS involvement.

---

## 2. Agent OS Entrypoint

### 2.1 Entrypoint Search Results

```yaml
search_paths:
  - /home/shade/.agents/
  - /home/shade/Public/test/
  - /home/shade/

searched_patterns:
  - launcher: NOT FOUND
  - bootstrap: NOT FOUND
  - wrapper: NOT FOUND
  - entrypoint: NOT FOUND
  - main: NOT FOUND (except loop_controller.py __main__)
  - cli: NOT FOUND (except loop_controller.py CLI)
  - runner: NOT FOUND
  - AGENTS.md: FOUND (but all are external tools' configs, not Agent OS)
  - CLAUDE.md: FOUND (but all are Claude Code configs, not Agent OS)
  - opencode.json: NOT FOUND in project
  - .agentrc: NOT FOUND
```

### 2.2 Entrypoint Assessment

```yaml
agent_os_entrypoint:
  exists: false
  type: ENTRYPOINT_MISSING
  reason: >
    No file in /home/shade/.agents/ serves as an automatic entry point.
    There is no main.py, no launcher, no bootstrap script, no CLI wrapper,
    no OpenCode plugin, and no AGENTS.md that would auto-bootstrap the Agent OS.
```

---

## 3. Loop Controller Entrypoint

File: `/home/shade/.agents/runtime/loop-controller/loop_controller.py`

```yaml
loop_controller:
  callable: true
  call_method: python3 loop_controller.py <task_id> <task_text> [memory_mode] [model]
  entrypoint: |
    if __name__ == "__main__":
        if len(sys.argv) < 3:
            print("Usage: python3 loop_controller.py <task_id> <task_text> ...")
            sys.exit(1)
        task_id = sys.argv[1]
        task_text = sys.argv[2]
        ...
        result = run_loop(task_id, task_text, memory_mode, model)
  automatically_invoked: false
  manual_only: true
  function_importable: true (run_loop function)
  no_auto_trigger: true
```

**Finding**: Loop Controller is a CLI tool only. It can ONLY be invoked manually via `python3 loop_controller.py ...`. It cannot receive tasks automatically from OpenCode.

---

## 4. Runtime Adapter Entrypoint

File: `/home/shade/.agents/runtime/loop-controller/runtime_adapter.py`

```yaml
runtime_adapter:
  callable: true
  call_method: |
    from runtime_adapter import execute
    result = execute(task_id, task_text, decision_context, model)
  invocation: subprocess.run(["opencode", "run", "--format", "json", "--auto", "--model", model, prompt])
  direction: Agent_OS → OpenCode
  opencode_to_adapter: false
  adapter_to_opencode: true
  automatic: false
  only_called_by_loop_controller: true
```

**Finding**: Runtime Adapter wraps OpenCode CLI as a subprocess. It is called by Loop Controller, not the other way around. OpenCode does NOT call the Runtime Adapter.

---

## 5. Retrieval Adapter Entrypoint

File: `/home/shade/.agents/runtime/loop-controller/retrieval_adapter.py`

```yaml
retrieval_adapter:
  callable: true
  call_method: |
    from retrieval_adapter import adapt
    decision_context = adapt(task_id, task_text, memory_mode)
  automatic: false
  only_called_by_loop_controller: true
```

---

## 6. Router Entrypoint

```yaml
router:
  location: memory/skill-routing-matrix.md
  type: DOCUMENT (not executable)
  invoked_by: retrieval_adapter.classify_task()
  automatic: false
  only_called_by_loop_controller: true
```

---

## 7. Memory Entrypoint

```yaml
memory:
  retrieval: runtime/memory-feedback/retrieval/retrieval_optimizer.py
  invoked_by: retrieval_adapter.adapt()
  automatic: false
  only_called_by_loop_controller: true
```

---

## 8. Orchestrator Entrypoint

```yaml
orchestrator:
  location: memory/skill-routing-matrix.md (role selection rules)
  type: RULE-BASED (embedded in retrieval_adapter.py)
  invoked_by: retrieval_adapter.classify_task()
  automatic: false
  only_called_by_loop_controller: true
```

---

## 9. Trae Relationship

```yaml
trae:
  binary: /usr/share/trae-cn/trae-cn
  type: VS Code-based IDE
  config_dir: /home/shade/.config/Trae CN/
  role: CURRENT_AI_AGENT_HOST
  is_agent_os_bootstrap: false
  is_opencode_replacement: false
  relationship_to_opencode: >
    Trae is the IDE hosting this AI Agent conversation.
    This AI Agent (in Trae) has direct access to execute code, read files, and call OpenCode.
    Trae is NOT replacing Agent OS. Trae is the execution environment
    that the AI Agent uses to run tools like opencode, python3, etc.
  relationship_to_agent_os: >
    Trae does NOT auto-bootstrap Agent OS. The AI Agent in Trae
    manually invokes loop_controller.py when explicitly instructed.
    There is no automatic pipeline connection.
```

**Key Finding**: Trae is the current AI agent host (where this conversation is running). The AI agent inside Trae can call `opencode run` or `python3 loop_controller.py` directly, but does NOT automatically route tasks through Agent OS.

---

## 10. Current Real Call Graph

```
CURRENT REAL CALL GRAPH (what actually happens)

When "opencode run" is called directly:
┌──────────┐
│   User   │
└────┬─────┘
     │
     ▼
┌──────────┐
│  Trae    │ (IDE hosting AI Agent)
└────┬─────┘
     │
     ▼
┌──────────┐
│ OpenCode │ (direct CLI invocation)
└────┬─────┘
     │
     ▼
┌──────────┐
│  Model   │ (e.g., mimo-v2.5-free, ling-3.0-flash-fin-free)
└──────────┘

Agent OS is COMPLETELY BYPASSED.

When Agent OS is manually invoked:
┌──────────┐
│   User   │
└────┬─────┘
     │
     ▼
┌──────────────────┐
│ python3          │
│ loop_controller  │ (MANUAL CLI invocation)
│ .py RT-003 "..." │
└────┬─────────────┘
     │
     ├──► retrieval_adapter ──► retrieval_optimizer ──► Memory
     │
     ├──► classify_task ──► Router (regex rules)
     │
     └──► runtime_adapter ──► subprocess: opencode run ──► Model
          │
          └──► trace ──► collector ──► validator ──► promoter ──► reconciler
```

---

## 11. Intended Agent OS Call Graph

```
INTENDED AGENT OS GRAPH (what should happen)

┌──────────┐
│   User   │
└────┬─────┘
     │
     ▼
┌────────────────────┐
│ Agent OS           │
│ Entry Point        │  ← MISSING
│ (bootstrap/launch) │
└────┬───────────────┘
     │
     ▼
┌────────────────────┐
│ Loop Controller    │
│ (auto-invoked)     │
└────┬───────────────┘
     │
     ├──► Stage 1: Retrieval Adapter
     │    └──► classify_task (Router)
     │    └──► retrieval_optimizer (Memory)
     │
     ├──► Stage 2: Decision Support
     │    └──► memory → confirmation/modify
     │
     └──► Stage 3: Runtime Adapter
          └──► subprocess: opencode run
               │
               ▼
          ┌──────────┐
          │ OpenCode │
          └────┬─────┘
               │
               ▼
          ┌──────────┐
          │  Model   │
          └──────────┘
```

---

## 12. Missing Edge

```yaml
missing_edge:
  from: OpenCode (or Trae AI Agent)
  to: Agent OS Loop Controller
  description: >
    There is NO mechanism that automatically routes a task from
    OpenCode (or Trae AI Agent) into the Agent OS pipeline.
    The Loop Controller is a CLI-only tool that must be manually
    invoked with python3 loop_controller.py <task_id> <task_text>.
  gap: ENTRYPOINT_MISSING
  consequence: >
    Every direct "opencode run" invocation bypasses Router, Memory,
    Orchestrator, Trace, Collector, Validator, Promoter, and Reconciler.
```

---

## 13. Root Cause

```yaml
root_cause:
  primary: >
    Agent OS was designed as a LIBRARY of Python modules, not as
    an AUTO-BOOTSTRAPPED SYSTEM. The Loop Controller is the only
    integration point, and it requires manual CLI invocation.
  secondary: >
    OpenCode has no plugin/hook mechanism (or none was configured)
    to redirect tasks to Agent OS. The OpenCode config only has
    supermemory, dcp, notifier, and morph-fast-apply plugins.
  tertiary: >
    Trae is the current AI Agent host, but it does not auto-bootstrap
    Agent OS either. The AI Agent in Trae directly uses OpenCode
    without going through the Agent OS pipeline.
  evidence:
    - No AGENTS.md in project that references Agent OS
    - No OpenCode plugin for Agent OS
    - No wrapper/launcher/bootstrap script in /home/shade/.agents/
    - Loop Controller __main__ block is CLI-only
    - All LOOP state files were created by manual python3 invocations
    - OpenCode log shows direct model invocations (no Agent OS middleware)
```

---

## 14. Agent OS Current Level

```yaml
agent_os_current_level: LIBRARY

classification:
  - LIBRARY: |
      Agent OS components (retrieval_adapter, runtime_adapter, collector,
      validator, promoter, reconciler) are importable Python modules.
      They can be used programmatically but require an external caller.
  - NOT_PIPELINE: |
      The pipeline exists conceptually (execution-contract.yaml) but
      is not auto-executing. It requires manual trigger.
  - NOT_RUNTIME: |
      There is no persistent daemon or event loop that watches for
      tasks and auto-processes them.
  - NOT_AUTO_BOOTSTRAPPED: |
      There is no mechanism for automatic entry. Every invocation
      must be manual.
```

---

## 15. Historical Evidence: Why Some Tasks "Looked Like" Agent OS

```yaml
explanation: >
  All recorded LOOP states, traces, and feedback entries were created
  by MANUAL invocations of:
    python3 runtime/loop-controller/loop_controller.py <task_id> <task_text>

  These were executed during development and testing of the Agent OS
  itself (Phase 5.6 - 5.9). They were NOT auto-triggered by any
  OpenCode task.

evidence:
  - LOOP-20260831004559.yaml: "python3 loop_controller.py RT-003 '分析 MySQL 慢查询问题'"
  - LOOP-20260831022319.yaml: "python3 loop_controller.py PROJ-001-T001 'RAG 知识库检索优化'"
  - collector_state.yaml: all processed_traces from EXEC-1788090990 through EXEC-1788143000
  - All timestamps from August 31, 2026 (today)

conclusion: >
  Agent OS PIPELINE_AVAILABLE is true (components work when manually invoked).
  Agent OS PIPELINE_AUTO_BOOTSTRAP is MISSING (no automatic entry).
```

---

## 16. Recommended Bootstrap Architecture

### Option A: AGENTS.md / Project Bootstrap

```yaml
mechanism: >
  Place AGENTS.md in the project root (/home/shade/Public/test/AGENTS.md)
  with instructions that tell the AI Agent to route tasks through Agent OS.
pros:
  - Simple, no code changes
  - Works with any AI Agent that reads AGENTS.md
  - Transparent
cons:
  - Depends on AI Agent compliance (not guaranteed)
  - Only works per-project, not globally
  - AI Agent may ignore or override
reliability: LOW
transparency: HIGH
maintainability: HIGH
compatibility: HIGH
```

### Option B: OpenCode Wrapper Script

```yaml
mechanism: >
  Replace/alias opencode with a wrapper script that intercepts
  "opencode run" calls and routes them through loop_controller.py.
pros:
  - Transparent to user
  - Works at the shell level
  - Guaranteed interception
cons:
  - Fragile (opencode updates may break wrapper)
  - Must handle all opencode subcommands
  - Complex error handling
reliability: MEDIUM
transparency: LOW
maintainability: LOW
compatibility: MEDIUM
```

### Option C: CLI Launcher (Recommended)

```yaml
mechanism: >
  Create a simple CLI launcher script (agent-os or aos) that:
  1. Takes a task description
  2. Generates a task_id
  3. Calls loop_controller.run_loop()
  4. Returns results
  Usage: aos "分析 MySQL 慢查询问题"
pros:
  - Clean, explicit interface
  - No magic, fully transparent
  - Easy to maintain
  - Works standalone or in scripts
  - Can be used by AI Agents or humans
cons:
  - Requires user to use aos instead of opencode
  - Not automatic (still requires manual invocation)
reliability: HIGH
transparency: HIGH
maintainability: HIGH
compatibility: HIGH
```

### Option D: OpenCode Plugin/Hook

```yaml
mechanism: >
  Develop an OpenCode plugin that hooks into the task execution
  lifecycle and routes tasks through Agent OS before/after model invocation.
pros:
  - Fully automatic
  - No user behavior change needed
  - Integrated with OpenCode
cons:
  - Requires OpenCode plugin API (may not exist or be stable)
  - Complex to implement
  - Depends on OpenCode internals
  - May break with OpenCode updates
reliability: LOW
transparency: LOW
maintainability: LOW
compatibility: LOW
```

### Recommendation

**Option C (CLI Launcher)** is recommended as the primary entry point:

1. It is reliable and transparent
2. It does not depend on OpenCode internals
3. It can be used by both humans and AI Agents
4. It is trivial to implement and maintain

For true auto-bootstrap, Option C can be combined with:
- A shell alias (`alias opencode-run='aos'`)
- An AGENTS.md instruction telling AI Agents to use `aos` instead of `opencode run`
- A future OpenCode plugin when the API stabilizes

---

## 17. Implementation

```yaml
implementation: NOT_EXECUTED
reason: >
  Per audit instructions (Section 4: 严格禁止), this phase is
  READ ONLY. No modifications to Agent OS, OpenCode, or project.
  Design only.
```

---

## 18. Final Answers

### Question 1: Does "opencode run" auto-bootstrap Agent OS?

```text
NO. Direct opencode run bypasses Agent OS entirely.
OpenCode invokes the model directly without going through
Router, Memory, Orchestrator, or any Agent OS component.
```

### Question 2: Is "python3 loop_controller.py" manual-only?

```text
YES. Loop Controller is a CLI tool that requires manual
invocation with explicit task_id and task_text arguments.
It is not auto-triggered by any external event.
```

### Question 3: Does Trae currently serve as Agent OS bootstrap?

```text
NO. Trae is the IDE hosting the AI Agent conversation.
The AI Agent in Trae can manually invoke loop_controller.py,
but Trae does NOT auto-bootstrap Agent OS for every task.
```

### Question 4: Can OpenCode use Agent OS if Trae is closed?

```text
NO. Agent OS has no auto-bootstrap mechanism regardless of
whether Trae is running or not. The only way to use Agent OS
is manual invocation of loop_controller.py.
```

### Question 5: What is Agent OS currently?

```text
LIBRARY. Agent OS is a collection of Python modules that can
be imported and called programmatically. It is NOT a pipeline,
NOT a runtime, and NOT an auto-bootstrapped system.
```

---

## 19. Audit Summary

```
==================================================
AGENT OS BOOTSTRAP AUDIT
==================================================

DIRECT_OPEN_CODE:
AUTO_BOOTSTRAPS_AGENT_OS:
NO

AGENT_OS_ENTRYPOINT:
NONE (ENTRYPOINT_MISSING)

LOOP_CONTROLLER:
MANUAL

RUNTIME_ADAPTER:
MANUAL

TRAE_DEPENDENCY:
NO

CURRENT_CALL_GRAPH:
User → Trae → OpenCode → Model
(Agent OS BYPASSED)

INTENDED_CALL_GRAPH:
User → Agent OS Entry → Loop Controller → Router → Memory → Orchestrator → Runtime Adapter → OpenCode → Model

MISSING_EDGE:
OpenCode → Agent OS Entry Point

ROOT_CAUSE:
Agent OS was designed as a LIBRARY, not an AUTO-BOOTSTRAPPED SYSTEM.
No entry point, launcher, wrapper, plugin, or hook exists.

AGENT_OS_CURRENT_LEVEL:
LIBRARY

RECOMMENDED_FIX:
Option C: CLI Launcher (aos command)
Combined with AGENTS.md instruction for AI Agent compliance.

IMPLEMENTATION:
NOT_EXECUTED
```