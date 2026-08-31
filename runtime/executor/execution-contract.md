# Execution Contract

## 1. Purpose

This contract defines the interface between the Agent OS declarative layer and the Runtime Backend. It is the **single source of truth** for how tasks flow from Router → Memory → Orchestrator → Agent Invocation → Trace.

## 2. Execution Request

```yaml
ExecutionRequest:
  execution_id: "<uuid>"
  task_id: "<RT-XXX>"
  task_text: "<user request>"
  memory_mode: "<on|off>"
  model: "<provider/model>"
  timestamp: "<ISO8601>"
```

## 3. Pipeline Steps

```
ExecutionRequest
  ↓
Step 1: Router (read skills/meta/agent-router/SKILL.md, classify intent, select lead)
  ↓
Step 2: Memory Retrieval (if memory_mode=on) (read memory/retrieval-skill.md, compute scores)
  ↓
Step 3: Decision Support (read memory/decision-support-protocol.md, apply memory to decision)
  ↓
Step 4: Orchestrator (read skills/meta/agent-orchestrator/SKILL.md, form team)
  ↓
Step 5: Agent Invocation (call backend with constructed prompt)
  ↓
Step 6: Result Capture (record agent response)
  ↓
Step 7: Trace Generation (write execution trace to runtime/traces/)
```

## 4. Execution Result

```yaml
ExecutionResult:
  execution_id: "<uuid>"
  trace_id: "<uuid>"
  task_id: "<RT-XXX>"
  timestamp: "<ISO8601>"
  backend: "<name>"
  model: "<provider/model>"

  router:
    intent: "<classification>"
    lead_agent: "<role>"
    support_agents: ["<roles>"]
    confidence: "<low|medium|high>"
    reason: "<why>"

  memory_retrieval:
    mode: "<on|off>"
    total_retrieved: <N>
    memories_used: ["<ids>"]
    memories_considered: ["<ids>"]
    influence: "<none|confirmation|role_added|role_removed|...>"

  orchestrator:
    team_formed: <bool>
    team_size: <N>
    lead_role: "<role>"
    support_roles: ["<roles>"]
    anti_pattern_alert: <bool>

  agent_invocation:
    backend: "<name>"
    model: "<provider/model>"
    session_id: "<id>"
    tokens: {input: <N>, output: <N>}
    cost: <float>
    latency_ms: <N>

  agent_response: "<actual response text>"

  status: "<success|error|timeout>"
  errors: ["<error messages>"]
```

## 5. Trace Artifact

Every execution produces a trace file at:

```text
runtime/traces/<execution_id>.yaml
```

The trace file contains the full ExecutionResult plus:

```yaml
pipeline:
  step_timestamps:
    router_start: "<ISO8601>"
    router_end: "<ISO8601>"
    memory_start: "<ISO8601>"
    memory_end: "<ISO8601>"
    orchestrator_start: "<ISO8601>"
    orchestrator_end: "<ISO8601>"
    agent_start: "<ISO8601>"
    agent_end: "<ISO8601>"

decision_provenance:
  router_rules: ["<rules applied>"]
  memory_match_reasons: {"<memory_id>": ["<reasons>"]}
  orchestrator_rules: ["<rules applied>"]
```

## 6. Backend Adapter Interface

Each backend adapter must implement:

```text
invoke(prompt: str, model: str) -> InvocationResult
```

Where `InvocationResult`:
```yaml
session_id: "<id>"
response_text: "<text>"
tokens: {input: <N>, output: <N>}
cost: <float>
latency_ms: <N>
status: "<success|error>"
```

## 7. Invariant Rules

1. Every execution MUST have a unique `execution_id` and `trace_id`.
2. Every step MUST record timestamps.
3. The `agent_response` field MUST contain the actual model output, not human-written text.
4. If `memory_mode=off`, steps 2-3 are skipped and `memory_retrieval` is null.
5. Execution traces are immutable once written.