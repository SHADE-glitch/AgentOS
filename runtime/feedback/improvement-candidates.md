# Improvement Candidates

This file records concrete iteration opportunities for router and skill improvement.

## Template

```text
Issue:
Evidence:
Affected Component:
Proposed Change:
Expected Improvement:
Risk:
```

## Example

```text
Issue: RAG tasks are sometimes misrouted to llm-engineer
Evidence: Benchmark cases 21, 25, 29 show recurring route confusion
Affected Component: agent-router
Proposed Change: raise rag-engineer priority when retrieval, embeddings, chunking, or vector store terms are present
Expected Improvement: +10% routing accuracy in AI retrieval tasks
Risk: Low
```

## Rule

Every improvement candidate must be derived from real benchmark or failure evidence.
