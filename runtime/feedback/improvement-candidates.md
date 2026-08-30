# Improvement Candidates

This file records concrete iteration opportunities for router and skill improvement.

## Canonical storage

The operational proposal queue is under:

- `runtime/feedback/improvement-candidates/`
- `runtime/feedback/improvement-candidates/templates/improvement-proposal.md`

## Required fields

```text
Problem:
Evidence:
Root Cause:
Proposed Change:
Risk:
Validation:
Status:
```

## Example

```text
Problem: RAG tasks are sometimes misrouted to llm-engineer
Evidence: benchmark cases 21, 25, 29 and failure record F-003 show repeated route confusion
Root Cause: router underweights retrieval and vector-store terminology
Proposed Change: increase rag-engineer priority when terms like retrieval, embeddings, vector DB, chunking, or semantic search appear
Risk: low
Validation: run 5 new RAG routing benchmark cases, expect >90% correct routing
Status: Pending
```

## Rule

Every improvement candidate must be derived from real benchmark or failure evidence and must move through the human review gate before implementation.
