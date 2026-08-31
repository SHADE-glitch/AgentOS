```yaml
memory_id: T-006
type: task
created_at: 2026-08-30
source:
  type: benchmark
  task_id: ai-02
  run_id: round0
  mode: multi
  file: runtime/datasets/multi-agent/comparison/ai-02.yaml
category: ai
confidence: low
evidence_level: benchmark_evaluated
tags: [tool-calling, agent, llm, prompt-engineering, evaluation]
status: observed
```

# Tool-Calling Agent Design

## Task Context

- **Task**: Design an LLM agent with tool-calling capabilities
- **Difficulty**: medium
- **Single lead**: llm-engineer
- **Multi team**: llm-engineer, prompt-engineer, agent-engineer (3 roles)

## Execution Results

| mode | completeness | correctness | architecture_quality | maintainability | mean |
|------|-------------|-------------|---------------------|-----------------|------|
| single | 2 | 3 | 3 | 3 | 2.75 |
| multi | 4 | 4 | 5 | 4 | 4.25 |

- **quality_delta**: +1.50 (tied for largest gain)
- **cost_delta**: 1 (1 extra human review)
- **winner**: multi

## Key Lessons

1. Tied with backend-02 for the largest quality improvement (+1.50)
2. Multi-agent added robust error handling for tool execution failures
3. Comprehensive evaluation set with diverse tool-calling scenarios
4. Cost optimization strategies for tool calls
5. The prompt-engineer contributed structured tool descriptions and few-shot examples

## Important Decisions

- Tool definition schema and validation
- Error handling: retry, fallback, and graceful degradation for tool failures
- Evaluation framework: test cases covering normal, edge, and error scenarios
- Cost optimization: tool call batching and caching strategies

## Observed Result

Agent design tasks benefit from the trifecta of llm-engineer (model integration), prompt-engineer (tool descriptions), and agent-engineer (workflow design). The single-agent output was particularly weak (2.75), suggesting this task type is inherently multi-domain.