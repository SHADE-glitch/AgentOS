# Retrieval Test Cases

**Phase**: 5.3
**Purpose**: 10 test cases for evaluating Memory Retrieval quality

---

## Test Case Design

| # | test | query | expected behavior |
|---|------|-------|-------------------|
| R-01 | payment system | backend, payment, security | → T-004, F-002, P-002, E-007 |
| R-02 | RAG system | ai, rag, retrieval | → T-005, S-001, E-004 |
| R-03 | MySQL optimization | optimization, database, sql | → T-010, E-003, AP-001 |
| R-04 | high concurrency | optimization, distributed, concurrency | → T-009, E-006, T-002 |
| R-05 | frontend performance | frontend, performance, spa | → T-008, E-009, E-008 |
| R-06 | AI chatbot | ai, llm, agent | → T-006, S-001, E-005, E-010, E-011 |
| R-07 | simple SQL issue | optimization, database | → T-010, E-003 (NOT ai memories) |
| R-08 | simple CRUD | backend, crud | → E-002, E-003 (NOT architecture patterns) |
| R-09 | cross-domain system | architecture, backend, ai, distributed | → P-001, S-002, T-002, T-001 |
| R-10 | novel task (no history) | iot, embedded | → empty or low-confidence only |

---

## R-01: Payment System

```yaml
query:
  task_text: "Design a payment processing system with PCI-DSS compliance"
  category: backend
  difficulty: medium
  domains: [payment, security]
  roles: [backend-architect, security-engineer]
  keywords: [pci-dss, compliance]
```

## R-02: RAG System

```yaml
query:
  task_text: "Design a RAG system with vector store and retrieval"
  category: ai
  difficulty: medium
  domains: [rag, retrieval, ai]
  roles: [rag-engineer, llm-engineer]
  keywords: [vector-store, reranking, evaluation]
```

## R-03: MySQL Optimization

```yaml
query:
  task_text: "Optimize MySQL slow queries"
  category: optimization
  difficulty: easy
  domains: [database, sql]
  roles: [database-engineer]
  keywords: [mysql, slow-query, indexing]
```

## R-04: High Concurrency

```yaml
query:
  task_text: "Optimize a high concurrency system"
  category: optimization
  difficulty: hard
  domains: [distributed, concurrency, performance]
  roles: [distributed-system, backend-architect]
  keywords: [high-concurrency, optimization, rollback]
```

## R-05: Frontend Performance

```yaml
query:
  task_text: "Improve SPA performance and loading time"
  category: frontend
  difficulty: easy
  domains: [performance, spa]
  roles: [frontend-performance, frontend-architect]
  keywords: [spa, performance, bundle-size]
```

## R-06: AI Chatbot

```yaml
query:
  task_text: "Build an AI chatbot with tool-calling capabilities"
  category: ai
  difficulty: medium
  domains: [llm, agent, chatbot]
  roles: [llm-engineer, agent-engineer, prompt-engineer]
  keywords: [tool-calling, agent, prompt]
```

## R-07: Simple SQL Issue

```yaml
query:
  task_text: "Fix a slow SQL query on a small table"
  category: optimization
  difficulty: easy
  domains: [database, sql]
  roles: [database-engineer]
  keywords: [sql, query]
```

## R-08: Simple CRUD

```yaml
query:
  task_text: "Build a simple CRUD API for a todo list"
  category: backend
  difficulty: easy
  domains: [crud, api]
  roles: [backend-architect]
  keywords: [crud, api, rest]
```

## R-09: Cross-Domain System

```yaml
query:
  task_text: "Design a full-stack AI-powered order processing platform"
  category: architecture
  difficulty: hard
  domains: [architecture, backend, ai, distributed]
  roles: [system-architect, backend-architect, rag-engineer, distributed-system]
  keywords: [cross-domain, architecture, ai, order]
```

## R-10: Novel Task (No History)

```yaml
query:
  task_text: "Design an IoT sensor data pipeline for embedded devices"
  category: optimization
  difficulty: hard
  domains: [iot, embedded, data-pipeline]
  roles: [distributed-system]
  keywords: [iot, embedded, mqtt]
```

---

## Expected Outcomes Summary

| test | expected_top_memories | must_not_include | special_check |
|------|----------------------|------------------|---------------|
| R-01 | T-004, F-002, P-002, E-007 | T-005 (rag), T-006 (ai) | failure memory should rank high |
| R-02 | T-005, S-001, E-004, E-005 | T-004 (payment) | ai specialist synergy |
| R-03 | T-010, E-003, AP-001 | T-006 (ai), T-005 (ai) | team inflation guard |
| R-04 | T-009, E-006, T-002 | T-008 (spa), T-007 (frontend) | distributed patterns |
| R-05 | T-008, E-009, E-008 | T-004 (payment) | marginal benefit |
| R-06 | T-006, S-001, E-005, E-010, E-011 | T-004 (payment) | ai specialist coverage |
| R-07 | T-010, E-003 | T-005 (rag), T-006 (ai), S-001 (ai) | **no AI pollution** |
| R-08 | E-002, E-003 | P-001, P-002, T-001, T-002, T-009 | **no architecture pattern pollution** |
| R-09 | P-001, S-002, T-002, T-001 | T-010 (mysql), T-008 (spa) | cross-domain pattern |
| R-10 | empty or low only | T-004, T-005, P-001, etc. | **no history found** |

---

*Test cases defined. Ready for evaluation.*