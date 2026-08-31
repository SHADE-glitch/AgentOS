# Expected Retrieval Results

**Phase**: 5.3
**Purpose**: Human-annotated expected results for each test case

---

## R-01: Payment System

```yaml
expected:
  - memory_id: T-004
    reason: exact match — payment system with PCI-DSS, same category, all domains/roles/keywords match
    min_score: 0.40
  - memory_id: F-002
    reason: failure memory for card data conflict in payment system — should rank high due to type_boost
    min_score: 0.35
  - memory_id: P-002
    reason: security-first team formation pattern applies to payment with compliance
    min_score: 0.25
  - memory_id: E-007
    reason: security-engineer effectiveness data for payment tasks
    min_score: 0.15
must_not_include:
  - T-005  # RAG — unrelated
  - T-006  # tool-calling — unrelated
  - S-001  # AI — unrelated
```

## R-02: RAG System

```yaml
expected:
  - memory_id: T-005
    reason: exact match — RAG system design
    min_score: 0.40
  - memory_id: S-001
    reason: AI specialist synergy success pattern
    min_score: 0.30
  - memory_id: E-004
    reason: rag-engineer effectiveness
    min_score: 0.20
  - memory_id: E-005
    reason: llm-engineer effectiveness
    min_score: 0.15
must_not_include:
  - T-004  # payment — unrelated
  - F-002  # payment — unrelated
```

## R-03: MySQL Optimization

```yaml
expected:
  - memory_id: T-010
    reason: exact match — MySQL slow query optimization
    min_score: 0.40
  - memory_id: E-003
    reason: database-engineer effectiveness
    min_score: 0.20
  - memory_id: AP-001
    reason: team inflation anti-pattern (single-domain task)
    min_score: 0.15
must_not_include:
  - T-005  # RAG — unrelated
  - T-006  # tool-calling — unrelated
  - S-001  # AI — unrelated
```

## R-04: High Concurrency

```yaml
expected:
  - memory_id: T-009
    reason: exact match — high concurrency optimization
    min_score: 0.40
  - memory_id: E-006
    reason: distributed-system effectiveness
    min_score: 0.20
  - memory_id: T-002
    reason: seckill system (high concurrency, Lua, distributed)
    min_score: 0.15
must_not_include:
  - T-008  # SPA — unrelated
  - T-007  # admin — unrelated
```

## R-05: Frontend Performance

```yaml
expected:
  - memory_id: T-008
    reason: exact match — SPA performance optimization
    min_score: 0.40
  - memory_id: E-009
    reason: frontend-performance effectiveness
    min_score: 0.20
  - memory_id: E-008
    reason: frontend-architect effectiveness
    min_score: 0.15
must_not_include:
  - T-004  # payment — unrelated
```

## R-06: AI Chatbot

```yaml
expected:
  - memory_id: T-006
    reason: exact match — tool-calling agent design
    min_score: 0.40
  - memory_id: S-001
    reason: AI specialist synergy success pattern
    min_score: 0.25
  - memory_id: E-005
    reason: llm-engineer effectiveness
    min_score: 0.20
  - memory_id: E-010
    reason: prompt-engineer effectiveness
    min_score: 0.15
  - memory_id: E-011
    reason: agent-engineer effectiveness
    min_score: 0.15
must_not_include:
  - T-004  # payment — unrelated
```

## R-07: Simple SQL Issue

```yaml
expected:
  - memory_id: T-010
    reason: MySQL optimization (same category, same role)
    min_score: 0.30
  - memory_id: E-003
    reason: database-engineer effectiveness
    min_score: 0.20
must_not_include:
  - T-005  # RAG — AI pollution
  - T-006  # tool-calling — AI pollution
  - S-001  # AI — AI pollution
  - E-004  # rag-engineer — AI pollution
  - E-005  # llm-engineer — AI pollution
```

## R-08: Simple CRUD

```yaml
expected:
  - memory_id: E-002
    reason: backend-architect effectiveness
    min_score: 0.15
  - memory_id: E-003
    reason: database-engineer effectiveness
    min_score: 0.10
must_not_include:
  - P-001  # cross-domain — not applicable to simple CRUD
  - P-002  # security — not applicable
  - T-001  # AI SaaS architecture — unrelated
  - T-002  # seckill — unrelated
  - T-009  # high concurrency — unrelated
```

## R-09: Cross-Domain System

```yaml
expected:
  - memory_id: P-001
    reason: cross-domain collaboration pattern (4+ domains)
    min_score: 0.30
  - memory_id: S-002
    reason: cross-domain architecture success
    min_score: 0.25
  - memory_id: T-002
    reason: seckill system (architecture + backend + distributed)
    min_score: 0.20
  - memory_id: T-001
    reason: AI SaaS architecture (architecture + backend + AI)
    min_score: 0.15
must_not_include:
  - T-010  # MySQL — unrelated
  - T-008  # SPA — unrelated
```

## R-10: Novel Task (IoT / Embedded)

```yaml
expected:
  - memory_id: E-006
    reason: distributed-system effectiveness (only weak match on role)
    max_score: 0.20
  - any_other: max_score 0.15
special_check:
  - no high-confidence memories should appear
  - top-5 may be sparse or empty
  - retrieval note should indicate "no relevant engineering memory"
```

---

## Evaluation Metrics

### Definitions

```text
precision@k = |expected ∩ retrieved| / k
recall@k = |expected ∩ retrieved| / |expected|
pollution_rate = |retrieved - expected| / |retrieved|
hypothesis_contamination = count(hypothesis without warning) / total_retrieved
```

### Targets

| metric | target |
|--------|--------|
| precision@5 | >= 0.6 |
| recall@5 | >= 0.6 |
| pollution_rate | <= 0.4 |
| hypothesis_contamination | 0.0 |

---

*Expected results annotated. Ready for evaluation.*