# Phase 5.9.2.4 — PROJ-001-T001 Code-Specific Re-Analysis

**Date**: 2026-08-31
**Phase**: 5.9.2.4
**Task**: PROJ-001-T001 (RAG 知识库检索优化)
**Project**: aiview (PROJ-001)
**Model**: opencode/mimo-v2.5-free
**Mode**: read-only

---

## 1. Project Context

```yaml
project: PROJ-001
name: aiview (AI 面试练习系统)
path: /home/shade/Public/test
stack: Java 17, Spring Boot, MyBatis-Plus, MySQL
embedding: OpenAI-compatible REST API (via AiProperties config)
build: Maven / Gradle
```

## 2. Real RAG Execution Flow

```
HTTP POST /api/knowledge/search
  │
  ▼
RagController.java:59
  ├─ class: RagController
  ├─ method: search(@RequestBody SearchRequest)
  ├─ evidence: @PostMapping("/api/knowledge/search")
  └─ calls ragService.search(UserContext.currentUserId(), req)
  │
  ▼
RagService.java:118-149
  ├─ class: RagService
  ├─ method: search(Long userId, SearchRequest req)
  │
  ├─ [1] Query validation (line 119-123)
  │   ├─ query non-empty check
  │   └─ topK clamp [1,10], default 3
  │
  ├─ [2] Chunk loading (line 124-128)
  │   ├─ chunkMapper.selectList()
  │   ├─ inSql: "SELECT id FROM knowledge_base WHERE user_id = " + userId
  │   └─ ⚠ No LIMIT, no pagination — loads ALL chunks
  │
  ├─ [3] Query embedding (line 132)
  │   ├─ embeddingClient.embed(query)
  │   └─ OpenAiCompatibleEmbeddingClient → REST /embeddings
  │
  ├─ [4] KB name mapping (line 133-134)
  │   └─ kbMapper.selectList() → Map<id, name>
  │
  ├─ [5] Cosine similarity loop (line 138-146)
  │   ├─ For each chunk:
  │   │   ├─ parseVector(json) → JSON deserialize
  │   │   ├─ cosine(queryVec, chunkVec) → Java double loop
  │   │   └─ hits.add(SearchHitVO)
  │   └─ ⚠ O(n) linear scan, JSON parse per chunk
  │
  ├─ [6] Sort + topK (line 147-148)
  │   └─ sort by score DESC, limit(topK)
  │
  └─ returns List<SearchHitVO>
```

## 3. Code Evidence — Verified Findings

### F-001: O(n) 全量分块线性扫描 (HIGH)

```yaml
file: RagService.java
method: search
line_range: 124-148
classification: FACT
severity: HIGH
confidence: HIGH

evidence: |
  RagService.java:124-128:
    chunkMapper.selectList(
        new LambdaQueryWrapper<KnowledgeChunk>()
            .inSql(KnowledgeChunk::getKbId,
                "SELECT id FROM knowledge_base WHERE user_id = " + userId
                        + " AND deleted = 0"));

  RagService.java:138-146:
    for (KnowledgeChunk chunk : chunks) {
        float[] vec = parseVector(chunk.getEmbedding());
        double score = cosine(queryVec, vec);
        hits.add(...);
    }

  All chunks loaded into memory. No LIMIT. No batch processing.
  Cosine computed per chunk in Java loop. JSON deserialized per chunk.
  With 10,000+ chunks, this becomes a significant bottleneck.

current_mitigation: none
```

### F-002: JSON 字符串存储 embedding 向量 (HIGH)

```yaml
file: KnowledgeChunk.java
field: embedding
line: 23
classification: FACT
severity: HIGH
confidence: HIGH

evidence: |
  KnowledgeChunk.java:23:
    private String embedding;  // JSON string in MySQL TEXT column

  RagService.java:209-218 (parseVector):
    var node = objectMapper.readTree(json);  // JSON parse every search
    float[] vec = new float[node.size()];
    for (int i = 0; i < node.size(); i++) {
        vec[i] = (float) node.get(i).asDouble();
    }

  RagService.java:220-226 (toJson):
    return objectMapper.writeValueAsString(vec);  // JSON serialize

  No native vector type (MySQL doesn't have one in standard edition).
  No vector index. No approximate nearest neighbor search.
  JSON parse + float deserialization on every search query.

current_mitigation: none
```

### F-003: inSql userId 拼接 (MEDIUM)

```yaml
file: RagService.java
method: search
line_range: 126-128
classification: FACT
severity: MEDIUM
confidence: HIGH

evidence: |
  RagService.java:126-128:
    .inSql(KnowledgeChunk::getKbId,
        "SELECT id FROM knowledge_base WHERE user_id = " + userId
                + " AND deleted = 0")

  userId (Long) concatenated directly into SQL string.
  MyBatis-Plus inSql() does not parameterize the subquery string.
  Mitigating factor: userId comes from UserContext (not user input),
  but defensive coding should use parameterized queries.

current_mitigation: userId is Long from internal UserContext, not raw user input
```

### F-004: 缺少 kb_id 过滤 (LOW)

```yaml
file: RagService.java, RagDtos.java
method: search, SearchRequest
line_range: 124-128 (RagService), 24-27 (RagDtos)
classification: FACT
severity: LOW
confidence: HIGH

evidence: |
  SearchRequest.java:24-27:
    public static class SearchRequest {
        private String query;
        private Integer topK = 3;
        // No kbId field
    }

  RagService.java:124-128:
    // Always searches ALL user knowledge bases
    .inSql(KnowledgeChunk::getKbId,
        "SELECT id FROM knowledge_base WHERE user_id = ...")

  No way to scope search to a specific knowledge base.

current_mitigation: none
```

### F-005: 无 Embedding 缓存 (LOW)

```yaml
file: RagService.java
method: addContent
line_range: 84-99
classification: INFERENCE
severity: LOW
confidence: MEDIUM

evidence: |
  RagService.java:84-99:
    List<String> pieces = chunkText(req.getContent());
    List<float[]> vectors = embeddingClient.embedAll(pieces);
    for (int i = 0; i < pieces.size(); i++) {
        chunk.setEmbedding(toJson(vectors.get(i)));
        chunkMapper.insert(chunk);
    }

  Re-embeds identical content on every addContent() call.
  No content hash or deduplication.

current_mitigation: none
```

## 4. Original Recommendations Review (Re-evaluated)

| # | Rec | Phase 5.9.2.2 | Phase 5.9.2.4 | Change |
|---|-----|--------------|--------------|--------|
| 1 | Chunking | GENERIC (Python LangChain) | PARTIAL_EVIDENCE (already has paragraph-aware splitting) | Same |
| 2 | Query Enhancement | GENERIC (Python HyDE) | GENERIC_RECOMMENDATION (no LLM client in project) | Same |
| 3 | Hybrid Search | GENERIC (Python BM25) | PARTIAL_EVIDENCE (valid concept, but requires Java-native BM25 or MySQL FULLTEXT) | Same |
| 4 | Reranking | GENERIC (Python CrossEncoder) | GENERIC_RECOMMENDATION (no Java-native CrossEncoder) | Same |
| 5 | Metadata Filtering | GENERIC (Python filters) | PARTIAL_EVIDENCE (kbId filter is the only applicable field) | Same |

**Key observation**: The re-classification did not change for any of the 5 original recommendations. The agent's output was fundamentally generic RAG best practices expressed as Python code. The code-specific re-analysis confirmed this.

## 5. Java-native Alternatives

Instead of the original 5 Python recommendations, the following are Java-native:

| Original | Python Approach | Java-native Alternative |
|----------|----------------|------------------------|
| Chunking | RecursiveCharacterTextSplitter | Already adequate (paragraph-aware + sliding window) |
| Query Enhancement | HyDE (Python LLM) | No LLM client in project — UNSUPPORTED |
| Hybrid Search | Python BM25 + RRF | MySQL FULLTEXT index on content column, combined with cosine score via RRF in Java |
| Reranking | Python CrossEncoder | Not feasible without external service — UNSUPPORTED for current stack |
| Metadata Filtering | Python dict filters | Add kbId to SearchRequest, use MyBatis-Plus .eq() |

## 6. New Project-Specific Findings (Agent Missed in First Analysis)

These are findings the first agent analysis did NOT identify:

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| F-001 | O(n) 全量分块线性扫描 | HIGH | RagService.java:124-148 |
| F-002 | JSON 字符串存储 embedding | HIGH | KnowledgeChunk.java:23 |
| F-003 | inSql userId 拼接 | MEDIUM | RagService.java:126-128 |
| F-004 | 缺少 kb_id 过滤 | LOW | SearchRequest.java:24-27 |
| F-005 | 无 Embedding 缓存 | LOW | RagService.java:84-99 |

## 7. Implementation Candidates

### Candidate A: Fix SQL injection — parameterized query

```yaml
title: 使用 MyBatis-Plus 参数化查询替换 inSql
files:
  - backend/src/main/java/com/aiview/rag/service/RagService.java
methods:
  - search
current_behavior: |
  .inSql(KnowledgeChunk::getKbId,
      "SELECT id FROM knowledge_base WHERE user_id = " + userId + " AND deleted = 0")
proposed_change: |
  // Step 1: Fetch kbIds with parameterized query
  List<Long> kbIds = kbMapper.selectList(
      new LambdaQueryWrapper<KnowledgeBase>()
          .select(KnowledgeBase::getId)
          .eq(KnowledgeBase::getUserId, userId))
      .stream().map(KnowledgeBase::getId).toList();

  if (kbIds.isEmpty()) return List.of();

  // Step 2: Use .in() which is parameterized
  List<KnowledgeChunk> chunks = chunkMapper.selectList(
      new LambdaQueryWrapper<KnowledgeChunk>()
          .in(KnowledgeChunk::getKbId, kbIds));
expected_benefit: 消除 SQL 注入风险，使用 MyBatis-Plus 参数化查询
risk: 多一次 DB 查询 (kbIds fetch)，但 kb 数量通常很少
rollback: 恢复原始 inSql 语句
verification:
  baseline: userId 拼接 SQL
  change: 参数化 .in() 查询
  metric: correctness (相同搜索结果)
  success_criteria: 搜索结果与修复前一致，无 SQL 注入向量
```

### Candidate B: Add kbId filter to SearchRequest

```yaml
title: 为 SearchRequest 添加可选 kbId 字段
files:
  - backend/src/main/java/com/aiview/rag/dto/RagDtos.java
  - backend/src/main/java/com/aiview/rag/service/RagService.java
methods:
  - SearchRequest (add field)
  - search (add filter)
current_behavior: 搜索所有用户知识库
proposed_change: |
  SearchRequest 添加:
    private Long kbId;

  RagService.search() 中:
    if (req.getKbId() != null) {
        wrapper.eq(KnowledgeChunk::getKbId, req.getKbId());
    }
expected_benefit: 支持按知识库搜索，减少无关结果
risk: 低 (新增字段，向后兼容)
rollback: 移除 kbId 字段，恢复原查询
verification:
  baseline: 搜索所有 KB
  change: 可选 kbId 过滤
  metric: correctness
  success_criteria: 指定 kbId 时搜索结果只包含该知识库内容
```

## 8. Verification Metrics

```yaml
metrics_available:
  query_latency: not_available (no baseline measurement)
  recall: not_available (no test dataset)
  precision: not_available (no test dataset)
  correctness: available (manual verification via API)

testing:
  existing_tests: none
  test_directory: backend/src/test (empty)
  approach: manual API verification for Candidates A and B
```

## 9. Security Findings

```yaml
security_finding:
  id: SEC-001
  severity: MEDIUM
  finding: inSql userId 拼接
  file: RagService.java
  line_range: 126-128
  evidence: |
    .inSql(KnowledgeChunk::getKbId,
        "SELECT id FROM knowledge_base WHERE user_id = " + userId
                + " AND deleted = 0")
  risk: |
    While userId is a Long from internal UserContext (not raw user input),
    string concatenation in SQL is a code smell. If UserContext is ever
    compromised or if the pattern is copied to user-input contexts,
    this becomes exploitable.
  recommended_fix: Candidate A — parameterized query
  priority: should be fixed before any other optimization
```

## 10. Agent Output Comparison — First vs Second Analysis

```yaml
comparison:
  first_analysis (Phase 5.9.2.2):
    execution_id: EXEC-1788143000
    model: opencode/mimo-v2.5-free
    session_id: ses_faa5f1f55ffeuG3OOlOfEsD9HA
    tokens: 26477
    latency_ms: 35688

    generic_recommendations: 5
    code_specific_references: 0
    python_code_examples: 5
    java_code_examples: 0
    project_files_read: 0 (speculative)
    line_number_references: 0
    FACT/INFERENCE/RECOMMENDATION: not distinguished

    recommendations:
      - chunking (Python LangChain)
      - query_enhancement (Python HyDE)
      - hybrid_search (Python BM25)
      - reranking (Python CrossEncoder)
      - metadata_filtering (Python dict)

  second_analysis (Phase 5.9.2.4):
    execution_id: (new)
    model: opencode/mimo-v2.5-free
    session_id: ses_faa54a29fffec7T9uzYs9B9JKo
    tokens: 28384
    latency_ms: 46100

    generic_recommendations: 0
    code_specific_references: 5
    python_code_examples: 0
    java_code_examples: 0 (conceptual Java/MyBatis-Plus)
    project_files_read: 2 (RagService.java, RagDtos.java)
    line_number_references: 5
    FACT/INFERENCE/RECOMMENDATION: partially distinguished

    findings:
      - SQL injection (RagService.java:127-128)
      - O(n) full scan (RagService.java:124-146)
      - No vector index (architectural)
      - No pagination/filtering (architectural)

  delta:
    generic_recommendations_before: 5
    evidence_backed_findings_after: 5
    false_or_weak_recommendations_removed: 5
    new_project_specific_findings: 5
    improvement: |
      Second analysis was code-specific. Zero Python code.
      All findings reference actual Java lines and methods.
      However, the second analysis was guided by a specific prompt
      that required code-level analysis. The first analysis was
      open-ended and produced generic RAG advice.
```

## 11. Human Review

```yaml
human_feedback: pending
overall_phase_5_9_2_3: neutral
  (5 original recommendations were generic Python code)

current_phase_5_9_2_4: |
  Re-analysis with code-specific prompt produced 5 concrete,
  code-evidenced findings. No Python code. All Java/MyBatis-Plus
  native recommendations. Implementation candidates are minimal,
  low-risk, and verifiable.
```

## 12. Implementation Decision

```yaml
decision: PROCEED

reason: |
  Two candidates (A: SQL injection fix, B: kbId filter) have:
  - DIRECT_EVIDENCE from actual Java code
  - Java-native solutions (MyBatis-Plus .in(), .eq())
  - Verifiable via manual API testing
  - Low risk, minimal files changed
  - Clear rollback path

  The original 5 agent recommendations remain DEFER/REDIRECTED.
  Implementation should proceed with the 2 code-evidenced candidates.

candidates_to_implement:
  - Candidate A: Fix SQL injection (SEC-001)
  - Candidate B: Add kbId filter to SearchRequest

files_to_change:
  - backend/src/main/java/com/aiview/rag/service/RagService.java
  - backend/src/main/java/com/aiview/rag/dto/RagDtos.java

estimated_change_size: ~20 lines
risk: low
rollback: simple revert
```

## 13. Evidence Level

```yaml
evidence_level: real_project_candidate
project_modified: NO (read-only analysis)
```

## 14. Limitations

```yaml
limitations:
  - no test data to validate search quality
  - no baseline metrics (latency, recall, precision)
  - no production traffic data
  - single working model (mimo-v2.5-free)
  - O(n) scan and JSON embedding storage are architectural issues
    that require larger changes (vector DB migration, index strategy)
    beyond the scope of minimal candidates
  - Hybrid search and reranking are not feasible without external
    services or significant infrastructure changes
```

---

Generated: 2026-08-31
Phase: 5.9.2.4