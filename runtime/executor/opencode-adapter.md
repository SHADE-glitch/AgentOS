# OpenCode Runtime Adapter

## 1. Identity

This adapter wraps the `opencode` CLI as the Agent OS Runtime Backend. It translates Agent OS `ExecutionRequest` into `opencode run` invocations and captures structured results.

## 2. Backend Metadata

```yaml
backend:
  name: opencode
  cli: "opencode run"
  version: "1.18.23"
  format: json
  auto_approve: true
  provider: opencode
  default_model: "opencode/ling-3.0-flash-fin-free"
  cost: free
```

## 3. Available Models

```yaml
free_models:
  - opencode/big-pickle
  - opencode/ling-3.0-flash-fin-free  # default
  - opencode/mimo-v2.5-free
  - opencode/muse-spark-1.2-contributor-free
  - opencode/nemotron-3-ultra-free
  - opencode/nemotron-3.5-lightning-free

github_copilot_models:
  - github-copilot/claude-sonnet-4.5
  - github-copilot/claude-sonnet-5
  - github-copilot/gpt-5.4
  - github-copilot/gpt-5.5
  - github-copilot/gemini-3.7-flash
  # ... (many more)
```

## 4. Invocation

```bash
opencode run \
  --format json \
  --auto \
  --model <provider/model> \
  '<prompt>'
```

### 4.1 Invocation Result Schema

```json
{
  "type": "text",
  "timestamp": 1788090194860,
  "sessionID": "ses_xxx",
  "part": {
    "id": "prt_xxx",
    "messageID": "msg_xxx",
    "sessionID": "ses_xxx",
    "type": "text",
    "text": "<actual response>",
    "time": {"start": 1788090194843, "end": 1788090194852}
  }
}
```

### 4.2 Token/Cost Schema

```json
{
  "type": "step_finish",
  "part": {
    "tokens": {
      "total": 24609,
      "input": 24580,
      "output": 4,
      "reasoning": 25,
      "cache": {"write": 0, "read": 0}
    },
    "cost": 0
  }
}
```

## 5. Adapter Implementation

```python
# Conceptual adapter (not executable — executed by AI Agent)

def invoke(prompt: str, model: str = "opencode/ling-3.0-flash-fin-free") -> InvocationResult:
    """
    Invoke OpenCode CLI with the given prompt and model.
    Returns structured invocation result.
    """
    command = [
        "opencode", "run",
        "--format", "json",
        "--auto",
        "--model", model,
        prompt
    ]
    
    # Execute command
    output = subprocess.run(command, capture_output=True, text=True, timeout=120)
    
    # Parse JSONL output
    result = parse_opencode_output(output.stdout)
    
    return InvocationResult(
        session_id=result.session_id,
        response_text=result.response_text,
        tokens=result.tokens,
        cost=result.cost,
        latency_ms=result.latency_ms,
        status="success"
    )
```

## 6. Prompt Construction

The adapter constructs the prompt by combining:

```text
[System Context: Agent OS Router/Orchestrator]
[Task: user request]
[Memory Context: retrieved memories (if memory_mode=on)]
[Instruction: execute the task as the assigned agent role]

You are acting as the {lead_agent} role.
Your task is: {task_text}

Memory context (use only if relevant):
{memory_context}

Execute the task and provide your result.
```

## 7. Error Handling

```yaml
errors:
  timeout: "opencode run exceeds 120s timeout"
  parse_error: "JSONL output cannot be parsed"
  session_error: "No session ID in output"
  empty_response: "No text response in output"
```

## 8. Limitations

- `opencode run` is a full agent (it can read files, execute commands). For simple text responses, this is overkill.
- The `--auto` flag bypasses permission prompts. Use with caution.
- Free models may have rate limits or quality constraints.
- The adapter is conceptually defined but executed by the AI Agent (Trae IDE), not by a standalone Python script.