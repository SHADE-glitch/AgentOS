# Phase 5.8.2.3.1A — Target Memory Correction (Corrected)

---

## Selection Correction

```yaml
previous_target: P-001
previous_reason_invalid: already_promoted (observation_count=2, evidence_level=runtime_validated, confidence=medium, status=active)
previous_task_a: RT-006
previous_task_b: RT-009

corrected_target: T-005
corrected_task_a: RT-002
corrected_task_b: RT-011
```

---

## 1. RT-006 Candidate Audit (Priority Check)

RT-006 "微服务治理方案" (EXEC-1788091972) 产生的 candidates:

| Candidate | Memory | Quality | Status | Issue |
|-----------|--------|---------|--------|-------|
| CAND-EXEC-1788091972-P-001 | P-001 | 0.45 | **already promoted** | observation_count=2, active |
| CAND-EXEC-1788091972-S-002 | S-002 | 0.45 | **already promoted** | observation_count=2, active |
| CAND-EXEC-1788091972-T-001 | T-001 | 0.45 | rejected | quality 0.45 << 3.0 |
| CAND-EXEC-1788091972-T-002 | T-002 | 0.45 | rejected | quality 0.45 << 3.0 |
| CAND-EXEC-1788091972-E-001 | E-001 | 0.45 | rejected | quality 0.45 << 3.0 |

**结论**: RT-006 无合适 candidate。所有非 promoted candidate 质量均为 0.45 (big-pickle fallback 模型)，远低于 3.0 阈值，且与 RT-009 无语义关联。

---

## 2. 全量 Candidate 筛选

从 17 个 memory 中筛选满足条件的:

```
observation_count = 1
promotion_status = not_promoted
quality >= 2.5 (reasonable proximity to 3.0 threshold)
```

| Memory | Type | Task A | Quality | Category | Tags |
|--------|------|--------|---------|----------|------|
| **T-005** | task | RT-002 | **2.95** | ai | rag, vector-store, retrieval, reranking, evaluation |
| S-001 | success | RT-002 | 2.95 | ai | ai, rag, tool-calling, specialist-synergy, multi-agent |
| E-004 | effectiveness | RT-002 | 2.95 | ai | rag-engineer, rag, retrieval, vector-store |
| E-005 | effectiveness | RT-002 | 2.95 | ai | llm-engineer, llm, model-integration, error-handling |
| T-010 | task | RT-003 | 2.65 | optimization | mysql, slow-query, single-domain |
| AP-001 | anti-pattern | RT-003 | 2.65 | optimization | team-inflation, single-domain |
| F-002 | failure | RT-004 | 2.55 | backend | payment, security, pci-dss |
| P-002 | pattern | RT-004 | 2.55 | cross-cutting | security, team-formation, compliance |
| T-004 | task | RT-004 | 2.55 | backend | payment-system, security, exactly-once |
| E-007 | effectiveness | RT-004 | 2.55 | backend | security-engineer, security, compliance |

---

## 3. 选择 Corrected Target: **T-005**

### 选择理由

1. **quality 最接近阈值**: 2.95 (仅差 0.05) — 任何 Task B 产生的 quality >= 3.0 即可通过
2. **明确工程语义**: RAG 系统设计 — 有具体的技术栈和评估标准
3. **未 promoted**: evidence_level 仍为 benchmark_evaluated, confidence=low, 无 observation_count
4. **有强语义匹配的 Task B**: RT-011 "向量库选型与召回策略" (同为 RAG 领域)
5. **Task A 独立证据真实**: EXEC-1788091469, session `ses_fad713c63ffeNKdUnTt19ljGId`, 真实 OpenCode 调用

### T-005 当前状态

```yaml
memory_id: T-005
file: memory/tasks/ai/rag.md
type: task
category: ai
evidence_level: benchmark_evaluated
confidence: low
tags: [rag, vector-store, retrieval, reranking, evaluation]
roles: [rag-engineer, llm-engineer, database-engineer]
status: observed
# observation_count: not present (implicitly 0 in index, 1 in validator)
```

### T-005 Validation 状态

```yaml
candidate_id: CAND-EXEC-1788091469-T-005
status: rejected
validation_runs: 1
quality_score: 2.95
rejection_reason: "Best quality score 2.95 below threshold 3.0"
unique_sessions: 1
evidence_sources: [EXEC-1788091469]
```

---

## 4. Corrected Task A: **RT-002**

```yaml
task_id: RT-002
user_request: "设计企业知识库问答系统"
task_domain: "AI / RAG"
execution_id: EXEC-1788091469
trace_id: TRACE-1788091469000000001
session_id: ses_fad713c63ffeNKdUnTt19ljGId
model: opencode/ling-3.0-flash-fin-free
status: success
```

---

## 5. Corrected Task B: **RT-011**

```yaml
task_id: RT-011
user_request: "向量库选型与召回策略"
task_domain: "AI / RAG"
expected_skills: [rag-engineer, database-engineer]
execution_status: NOT EXECUTED
```

### 语义相关性

| 维度 | T-005 (Target) | RT-011 (Task B) |
|------|---------------|-----------------|
| tags | rag, vector-store, retrieval, reranking, evaluation | rag-engineer, database-engineer |
| domain | AI / RAG | AI / RAG |
| 核心主题 | RAG 系统设计 | 向量库选型 + 召回策略 |
| 关联 | T-005 记录 RAG 系统设计经验 | RT-011 直接涉及向量库和检索 |

### 独立性验证

| 维度 | Task A (RT-002) | Task B (RT-011) |
|------|----------------|-----------------|
| task_id | RT-002 | RT-011 |
| user_request | 设计企业知识库问答系统 | 向量库选型与召回策略 |
| execution_id | EXEC-1788091469 | (待生成) |
| trace_id | TRACE-1788091469000000001 | (待生成) |
| session_id | ses_fad713c63ffeNKdUnTt19ljGId | (待生成) |

---

## 6. RT-009 淘汰说明

RT-009 不满足 `与 Target Memory 有明确语义关系` 条件:

- RT-009 "订单服务拆分方案" 属于 Backend/Architecture 域
- T-005 属于 AI/RAG 域
- 无语义重叠

因此 RT-009 不保留为 Task B。

---

## 7. 预期 Closed-Loop 路径

```
RT-002 (Task A)
  → T-005 used: true (confirmation)
  → Candidate A: CAND-EXEC-1788091469-T-005 (quality=2.95)
  → Validator: rejected (quality 2.95 < 3.0, 1 observation)

RT-011 (Task B, 待执行)
  → T-005 expected: used (RAG 语义匹配)
  → Candidate B: (expected quality >= 3.0)
  → Validator: 2 independent observations
  → Expected: validated (best quality >= 3.0, M4 satisfied)
  → Promoter: observation_count 0→1→2, evidence_level benchmark→runtime, confidence low→medium
```

---

## 8. 合规检查

- [x] Target Memory = not already promoted (T-005: benchmark_evaluated, low)
- [x] Task A = valid evidence (RT-002, EXEC-1788091469, real session)
- [x] Task B = independent (different task_id, not executed)
- [x] Target Memory relevant to Task B (both RAG domain)
- [x] Promotion path = possible (quality 2.95, just 0.05 below threshold)
- [x] 未修改 M4 或降低 promotion 标准
- [x] 未选择已 promoted 的 Memory (P-001, S-002)

---

Generated: 2026-08-31
Phase: 5.8.2.3.1A
Status: Correction Complete — Awaiting Approval