```yaml
memory_id: S-001
type: success
created_at: 2026-08-30
source:
  type: benchmark
  sources:
    - task_id: ai-01
      run_id: round0
      mode: multi
    - task_id: ai-02
      run_id: round0
      mode: multi
category: ai
confidence: low
evidence_level: benchmark_evaluated
tags: [ai, rag, tool-calling, specialist-synergy, multi-agent]
status: observed
```

# S-001: AI Specialist Synergy

## What Worked

AI tasks (RAG design, tool-calling agent) showed the strongest multi-agent benefit in Round 0, with an average quality delta of +1.38.

## Why It Worked

The AI specialist trifecta proved highly effective:
- **rag-engineer**: retrieval architecture, vector store selection, evaluation methodology
- **llm-engineer**: model integration, response generation, error handling
- **prompt-engineer**: structured tool descriptions, few-shot examples, output formatting
- **agent-engineer**: workflow design, tool orchestration, state management
- **database-engineer**: storage optimization, indexing for vector data

Each specialist contributed a distinct dimension that the single-agent (operating alone) could not fully cover.

## Contributing Roles

| role | contribution in ai-01 | contribution in ai-02 |
|------|----------------------|----------------------|
| rag-engineer | vector store comparison, two-stage retrieval | N/A |
| llm-engineer | model selection, integration | model integration, error handling |
| database-engineer | vector storage optimization | N/A |
| prompt-engineer | N/A | tool descriptions, few-shot examples |
| agent-engineer | N/A | workflow design, orchestration |

## Conditions

- Task requires 3+ distinct AI sub-domains
- At least one infrastructure concern (storage, performance)
- Evaluation methodology is part of the deliverable

## Limitations

- Only 2 AI tasks observed in Round 0
- Not tested on simpler AI tasks (e.g., single prompt optimization)
- The synergy may not generalize to all AI task types

## Evidence Level

`benchmark_evaluated` — 2 observations. Confidence is low. More AI tasks needed for validation.