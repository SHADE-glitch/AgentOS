# Routing Error Classification

This file classifies route mistakes so the router can be improved systematically.

## Error Types

### Type A: Wrong Lead Skill

Example:
- RAG request routed to `llm-engineer` instead of `rag-engineer`
- SQL problem routed to `backend-architect` instead of `database-engineer`

### Type B: Missing Supporting Skill

Example:
- system design request assigned to `system-architect` without `database-engineer` or `distributed-system`

### Type C: Skill Boundary Conflict

Example:
- `backend-architect` and `system-architect` both claim the same task without a clear boundary

### Type D: Fallback Failure

Example:
- ambiguous task should have fallen back to `system-architect` but was routed to a less suitable specialist

## Template

```text
Date:
Task:
Error Type: A / B / C / D
Expected Lead Skill:
Actual Lead Skill:
Supporting Skills Missing:
Root Cause:
Proposed Fix:
```

## Example

```text
Date: 2026-08-30
Task: RAG 系统问答平台
Error Type: A
Expected Lead Skill: rag-engineer
Actual Lead Skill: llm-engineer
Supporting Skills Missing: prompt-engineer
Root Cause: router over-weighted model integration and under-weighted retrieval strategy.
Proposed Fix: raise rag-engineer priority when tasks involve retrieval, embeddings, chunking, or vector store.
```

## Rule

Every routing failure must be recorded with a concrete fix direction.
