# Improvement Candidate IC-001

## Problem
RAG tasks are sometimes misrouted to llm-engineer despite retrieval and embedding requirements dominating the task.

## Evidence
- Failure records: F-001, F-005
- Benchmark: router baseline 58 cases, 3 wrong lead routes in retrieval-heavy tasks
- Runtime signal: terms like retrieval, embedding, vector DB, semantic search, chunking were not weighted strongly enough

## Root Cause
The router underweights retrieval terminology and overweights generic model integration wording.

## Proposed Change
- Increase rag-engineer priority when user intents mention retrieval, embeddings, vec­tor DB, chunking, or semantic search
- Require database-engineer support on vector-store and indexing tasks
- Keep llm-engineer as a supporting role unless the task is primarily model API integration

## Risk
Low; this change only refines domain classification for retrieval-heavy tasks.

## Validation
- Run 5 new RAG benchmark cases
- Expect >90% lead-skill accuracy on retrieval tasks
- Human review required before implementation

## Status
Approved
