# Phase 5.9.2.3 — PROJ-001-T001 Human Review & Implementation Decision

**Date**: 2026-08-31
**Phase**: 5.9.2.3
**Task**: PROJ-001-T001 (RAG 知识库检索优化)

---

## 1. Task

```yaml
task_id: PROJ-001-T001
task_text: RAG 知识库检索优化
project: aiview (PROJ-001)
trace: EXEC-1788143000
model: opencode/mimo-v2.5-free
```

## 2. Agent Recommendations

The agent proposed 5 optimization directions:

| # | Recommendation | Agent's Priority | Agent's Complexity |
|---|---------------|-----------------|-------------------|
| 1 | Chunking optimization | Phase 1 | Low |
| 2 | Query Enhancement (HyDE) | Phase 4 | High |
| 3 | Hybrid Search (BM25) | Phase 2 | Medium |
| 4 | Reranking (CrossEncoder) | Phase 3 | Medium |
| 5 | Metadata Filtering | Not prioritized | Not specified |

**Critical observation**: All 5 recommendations include Python code examples (LangChain, sentence_transformers, CrossEncoder). This is a Java/Spring Boot project using MyBatis-Plus.

## 3. Code Evidence

### Source files reviewed

| File | Lines | Purpose |
|------|-------|---------|
| RagService.java | 239 | Core RAG service (search, chunking, CRUD) |
| KnowledgeChunk.java | 29 | Entity: id, kbId, title, content, embedding, createdAt |
| RagDtos.java | 58 | DTOs: SearchRequest, SearchHitVO, etc. |
| EmbeddingClient.java | 12 | Interface: embed(text) → float[] |
| OpenAiCompatibleEmbeddingClient.java | 80+ | OpenAI-compatible embedding via REST |
| RagController.java | 62 | REST API: /api/knowledge/search, etc. |
| KnowledgeChunkMapper.java | 9 | MyBatis-Plus BaseMapper (empty) |
| KnowledgeBaseMapper.java | 9 | MyBatis-Plus BaseMapper (empty) |

### Key code findings

**`search()` method (RagService.java:118-149)**:
```java
// Line 124-128: Full table scan — loads ALL chunks into memory
List<KnowledgeChunk> chunks = chunkMapper.selectList(
    new LambdaQueryWrapper<KnowledgeChunk>()
        .inSql(KnowledgeChunk::getKbId,
            "SELECT id FROM knowledge_base WHERE user_id = " + userId
                    + " AND deleted = 0"));

// Line 138-146: O(n) linear cosine computation
for (KnowledgeChunk chunk : chunks) {
    float[] vec = parseVector(chunk.getEmbedding());  // JSON parse per chunk
    double score = cosine(queryVec, vec);
    hits.add(...);
}

// Line 147-148: Simple sort, no reranking
hits.sort(Comparator.comparingDouble(RagDtos.SearchHitVO::getScore).reversed());
return hits.stream().limit(topK).toList();
```

**`chunkText()` method (RagService.java:179-203)**:
```java
// Already paragraph-aware: splits by double newline first
String[] paragraphs = normalized.split("\n\\s*\n");

// Then sliding window with 500/50 for oversized paragraphs
int start = 0;
while (start < p.length()) {
    int end = Math.min(start + CHUNK_SIZE, p.length());
    pieces.add(p.substring(start, end).trim());
    start = Math.max(end - CHUNK_OVERLAP, start + 1);
}
```

**Vector storage (KnowledgeChunk.java:23)**:
```java
private String embedding;  // JSON string, not native vector type
```

## 4. Recommendation Classification

### 1. Chunking — PARTIAL_EVIDENCE

```yaml
code_evidence:
  current_implementation: |
    RagService.java:179-203 — Paragraph-aware splitting with sliding window (500/50).
    Already uses semantic boundaries (paragraphs) before fixed-size fallback.
  identified_problem: |
    Agent claims chunking needs improvement. But current implementation is
    already reasonable for this project's scale.
  agent_proposal: |
    Python LangChain RecursiveCharacterTextSplitter — not applicable to Java.
  severity: low
  confidence: low
  change_scope: N/A (current implementation is adequate)
```

### 2. Query Enhancement — GENERIC_RECOMMENDATION

```yaml
code_evidence:
  current_implementation: |
    RagService.java:118 — Direct query embedding, no rewriting.
  identified_problem: |
    Agent assumes query problems exist. No code evidence of query failures.
  agent_proposal: |
    HyDE + Query Decomposition — requires LLM integration not present in codebase.
    No Java LLM client exists in the reviewed files.
  severity: unknown
  confidence: low
  change_scope: large (new LLM integration, new API calls, increased latency)
```

### 3. Hybrid Search — PARTIAL_EVIDENCE

```yaml
code_evidence:
  current_implementation: |
    RagService.java:138-148 — Cosine similarity only. No keyword search.
  identified_problem: |
    Pure vector search may miss exact keyword matches.
  agent_proposal: |
    Python BM25 + RRF fusion — Python-specific. Java alternative: MySQL FULLTEXT.
  severity: medium
  confidence: medium
  change_scope: medium (BM25 index or MySQL FULLTEXT index)
```

### 4. Reranking — GENERIC_RECOMMENDATION

```yaml
code_evidence:
  current_implementation: |
    RagService.java:147 — Cosine similarity sort only. No reranking.
  identified_problem: |
    Cosine similarity alone may not capture semantic relevance.
  agent_proposal: |
    Python CrossEncoder (sentence_transformers) — Python-specific.
    No Java-native reranker proposed.
  severity: medium
  confidence: low
  change_scope: large (would need Java CrossEncoder equivalent or API service)
```

### 5. Metadata Filtering — PARTIAL_EVIDENCE

```yaml
code_evidence:
  current_implementation: |
    RagService.java:124-128 — Filters by userId only via subquery.
    KnowledgeChunk entity: id, kbId, title, content, embedding, createdAt.
  identified_problem: |
    No kb_id filtering. Search returns results from ALL user knowledge bases.
  agent_proposal: |
    Python metadata filters (doc_type, version, language) — fields don't exist
    in the entity schema.
  severity: low
  confidence: medium
  change_scope: small (add optional kbId filter to SearchRequest)
```

## 5. Code-Level Issues Agent Missed

The code review identified issues the agent did NOT mention:

| # | Issue | Location | Severity | Evidence |
|---|-------|----------|----------|----------|
| 1 | O(n) linear scan of all chunks | RagService.java:124-148 | HIGH | Loads all chunks into memory, computes cosine for each |
| 2 | JSON vector storage in MySQL | KnowledgeChunk.java:23 | HIGH | No vector index, JSON parse per search |
| 3 | SQL injection risk | RagService.java:126-127 | MEDIUM | userId concatenated into inSql |
| 4 | No kb_id filtering | RagService.java:124-128 | LOW | All user KBs searched together |
| 5 | No batch/pagination | RagService.java:124 | MEDIUM | No limit on chunk loading |

## 6. Candidate Changes

### Candidate A: Add kbId filter to search API

```yaml
implementation_candidate:
  files:
    - backend/src/main/java/com/aiview/rag/dto/RagDtos.java
    - backend/src/main/java/com/aiview/rag/service/RagService.java
  proposed_change: |
    Add optional kbId field to SearchRequest.
    If kbId is provided, filter chunks by kbId instead of all user KBs.
  expected_benefit: |
    Allows targeted search within a specific knowledge base.
    Reduces chunk count when kbId is specified.
  risk: low
  rollback: remove kbId field, revert to original query
  before: search all user KBs
  after: optional kbId filter
  measurement: not_available (no test data)
  success_criteria: search returns results filtered by kbId when specified
```

### Candidate B: Fix SQL injection in inSql

```yaml
implementation_candidate:
  files:
    - backend/src/main/java/com/aiview/rag/service/RagService.java
  proposed_change: |
    Replace inSql with parameterized query or use MyBatis-Plus apply() with
    parameter binding. Extract kbId list first, then use .in().
  expected_benefit: |
    Eliminates SQL injection risk. userId is internal but defensive coding.
  risk: minimal
  rollback: revert to original inSql
  before: userId concatenated in SQL string
  after: parameterized query
  measurement: not_available
  success_criteria: same search results, no SQL injection vector
```

## 7. Testing Strategy

```yaml
existing_tests: none
test_directory: backend/src/test (empty)
test_framework: unknown (no test files found)

testing_approach: |
  No existing tests for RAG module. Any implementation would require:
  1. Writing new tests from scratch
  2. Mocking EmbeddingClient for deterministic results
  3. Setting up test data in KnowledgeChunk/KnowledgeBase tables

  For minimal changes (Candidate A/B), manual verification via API
  would be sufficient. For larger changes, unit tests would be needed.
```

## 8. Risk

```yaml
risks:
  - agent_recommendations: all generic, Python-specific, not code-evidenced
  - no_tests: zero test coverage for RAG module
  - no_metrics: no baseline latency, recall, or accuracy data
  - single_model: mimo-v2.5-free is the only working model

mitigation: |
  Only implement changes with DIRECT_EVIDENCE from code review.
  Start with minimal, safe changes (Candidate A/B).
  Do not implement any of the 5 agent recommendations without
  further code-specific analysis.
```

## 9. Human Review

See: [PROJ-001-T001-review.yaml](file:///home/shade/.agents/runtime/datasets/real-project/feedback/PROJ-001-T001-review.yaml)

```yaml
overall: neutral
helpful: false
harmful: false
```

## 10. Memory Influence

```yaml
original: confirmation
reclassified: confirmation
analysis: |
  5 memories retrieved with low relevance (0.306-0.358).
  Agent output was generic RAG advice, not project-specific.
  No evidence memories caused any decision change.
  Memories confirmed the agent's approach but added no project-specific value.
```

## 11. Implementation Decision

```yaml
decision: DEFER

reason: |
  All 5 agent recommendations are generic RAG best practices expressed as
  Python code examples. None are specific to this Java/Spring Boot/MyBatis-Plus
  project. The agent did not reference specific line numbers, did not analyze
  the actual Java implementation, and did not propose Java-native solutions.

  The code review revealed actual code-level issues (O(n) scan, JSON vector
  storage, SQL injection risk) that the agent did not identify. These are
  more actionable than the agent's generic recommendations.

  Before implementing any changes, a code-specific analysis is needed that:
  1. References actual Java source files and line numbers
  2. Proposes Java-native solutions (not Python libraries)
  3. Considers the existing tech stack (Spring Boot, MyBatis-Plus, MySQL)
  4. Addresses the actual code issues (O(n) scan, JSON storage, SQL injection)
```

## 12. Evidence Level

```yaml
evidence_level: real_project_candidate
```

## 13. Limitations

```yaml
limitations:
  - no test data to validate search quality
  - no baseline metrics (latency, recall, accuracy)
  - no production traffic data
  - agent output was generic, not code-specific
  - single working model (mimo-v2.5-free)
```

---

Generated: 2026-08-31
Phase: 5.9.2.3