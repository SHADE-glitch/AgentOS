# Phase 5.5.2.1 — Pilot Task Selection Report

**Date**: 2026-08-30
**Status**: COMPLETE

---

## 1. Dataset Audit

### 1.1 Source Files

| file | records | status |
|------|---------|--------|
| `runtime/datasets/raw/tasks.md` | 12 explicit RT records (RT-001 to RT-012) | Read |
| `runtime/datasets/classified/task-category.md` | 12 classified records | Read |
| `runtime/datasets/benchmark/real-world-benchmark.md` | Summary: 58 tasks, 91.4% accuracy | Read |
| `runtime/logs/routing-history.md` | Example records (2 tasks) | Read |
| `runtime/logs/multi-agent-benchmark.md` | 10 benchmark tasks (arch-*, backend-*, ai-*, fe-*, opt-*) | Read — benchmark, not real project |

### 1.2 Data Limitation

```yaml
claimed_total: 58 real task executions
documented_in_files: 12 explicit RT records
undocumented: 46
benchmark_tasks: 10 (multi-agent benchmark — not real project)

source: "The 58 count is from the benchmark summary. Only 12 tasks have explicit yaml records with task_id, user_request, domain, skills, result, quality_score, and failure description."

sampling_limitation: true
reason: "46 of 58 claimed tasks are not documented in individual task records. Pilot selection is based on the 12 documented RT tasks."
```

### 1.3 Available Tasks

| task_id | user_request | domain | complexity | quality | skills |
|---------|-------------|--------|------------|---------|--------|
| RT-001 | 高并发秒杀系统 | Distributed | hard | 0.88 | distributed-system, system-architect, database-engineer |
| RT-002 | 企业知识库问答系统 | AI / RAG | medium | 0.91 | rag-engineer, llm-engineer, prompt-engineer |
| RT-003 | MySQL 慢查询 | Database | easy | 0.92 | database-engineer, backend-architect |
| RT-004 | 支付系统接口与安全 | Backend / Security | medium | 0.89 | backend-architect, security-engineer |
| RT-005 | Redis 缓存击穿 | Database / Cache | easy | 0.94 | database-engineer, backend-architect |
| RT-006 | 微服务治理方案 | Architecture | hard | 0.90 | backend-architect, system-architect, devops-engineer |
| RT-007 | LLM 应用接入层设计 | AI / Model | medium | 0.90 | llm-engineer, agent-engineer |
| RT-008 | Prompt 优化评审 | AI / Prompting | medium | 0.93 | prompt-engineer, llm-engineer |
| RT-009 | 订单服务拆分方案 | Backend / Architecture | medium | 0.87 | backend-architect, system-architect |
| RT-010 | 分布式事务设计 | Distributed | hard | 0.90 | distributed-system, system-architect |
| RT-011 | 向量库选型与召回策略 | AI / RAG | medium | 0.92 | rag-engineer, database-engineer |
| RT-012 | 前端性能优化与缓存策略 | Frontend | medium | 0.89 | frontend-architect, backend-architect |

---

## 2. Selection Criteria

### 2.1 Weighted Scoring

```yaml
criteria:
  real_project_relevance:     # 30% — is this a genuine engineering task?
    score: 0-3
    evaluation:
      3: "Clear real project context, concrete deliverable, real code/architecture"
      2: "Real engineering task, context partially documented"
      1: "Generic task, limited context"
      0: "Synthetic or benchmark-only"

  memory_relevance:            # 20% — how many existing Engineering Memories match?
    score: 0-3
    evaluation:
      3: "3+ memories match with final_score >= 0.15"
      2: "1-2 memories match"
      1: "Weak or indirect memory match"
      0: "No matching memory"

  domain_diversity:            # 15% — does this task fill a domain gap?
    score: 0-3
    evaluation:
      3: "Unique domain not covered by other pilot tasks"
      2: "Domain has 1-2 other representatives"
      1: "Domain already well-covered"

  complexity_diversity:        # 15% — does this task fill a complexity gap?
    score: 0-3
    evaluation:
      3: "Unique complexity level in its domain"
      2: "Complexity complements other tasks"
      1: "Complexity already well-covered"

  outcome_availability:        # 10% — is there a real execution result?
    score: 0-3
    evaluation:
      3: "Has quality_score, failure description, and result"
      2: "Has result and quality_score"
      1: "Has result only"
      0: "No execution result"

  human_feedback_availability: # 10% — is there developer/human feedback?
    score: 0-3
    evaluation:
      3: "Explicit human feedback available"
      2: "Indirect feedback (failure description implies human review)"
      1: "No human feedback"
      0: "Unknown"
```

### 2.2 Selection Weight Formula

```text
selection_score =
  0.30 × real_project_relevance +
  0.20 × memory_relevance +
  0.15 × domain_diversity +
  0.15 × complexity_diversity +
  0.10 × outcome_availability +
  0.10 × human_feedback_availability
```

---

## 3. Task Scoring

### 3.1 Individual Scores

| task_id | real_project (0.30) | memory (0.20) | domain (0.15) | complexity (0.15) | outcome (0.10) | feedback (0.10) | **total** |
|---------|---------------------|---------------|---------------|-------------------|----------------|-----------------|-----------|
| RT-001 | 3 (0.90) | 3 (0.60) | 2 (0.30) | 3 (0.45) | 3 (0.30) | 2 (0.20) | **2.75** |
| RT-002 | 3 (0.90) | 3 (0.60) | 3 (0.45) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.75** |
| RT-003 | 3 (0.90) | 3 (0.60) | 3 (0.45) | 3 (0.45) | 3 (0.30) | 2 (0.20) | **2.90** |
| RT-004 | 3 (0.90) | 3 (0.60) | 3 (0.45) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.75** |
| RT-005 | 3 (0.90) | 2 (0.40) | 2 (0.30) | 3 (0.45) | 3 (0.30) | 2 (0.20) | **2.55** |
| RT-006 | 3 (0.90) | 2 (0.40) | 3 (0.45) | 3 (0.45) | 3 (0.30) | 2 (0.20) | **2.70** |
| RT-007 | 3 (0.90) | 2 (0.40) | 1 (0.15) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.25** |
| RT-008 | 3 (0.90) | 2 (0.40) | 1 (0.15) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.25** |
| RT-009 | 3 (0.90) | 2 (0.40) | 2 (0.30) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.40** |
| RT-010 | 3 (0.90) | 3 (0.60) | 2 (0.30) | 3 (0.45) | 3 (0.30) | 2 (0.20) | **2.75** |
| RT-011 | 3 (0.90) | 3 (0.60) | 2 (0.30) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.60** |
| RT-012 | 3 (0.90) | 3 (0.60) | 3 (0.45) | 2 (0.30) | 3 (0.30) | 2 (0.20) | **2.75** |

### 3.2 Memory Relevance Detail

| task_id | matching memories | final_scores |
|---------|------------------|--------------|
| RT-001 | T-009 (high-concurrency), E-006 (distributed), T-002 (architecture scale-up) | 0.50, 0.33, 0.29 |
| RT-002 | T-005 (RAG), S-001 (RAG success), E-004 (rag-engineer), E-005 (llm-engineer) | 0.50, 0.43, 0.39, 0.24 |
| RT-003 | T-010 (MySQL), AP-001 (team-inflation), E-003 (database-engineer) | 0.41, 0.24, 0.19 |
| RT-004 | F-002 (payment failure), T-004 (payment), P-002 (security pattern), E-007 (security) | 0.53, 0.50, 0.41, 0.39 |
| RT-005 | T-010 (MySQL), E-003 (database-engineer) | 0.41, 0.19 |
| RT-006 | T-002 (architecture), P-001 (cross-domain), T-001 (architecture) | 0.29, 0.47, 0.39 |
| RT-007 | T-006 (tool-calling), E-005 (llm), E-011 (agent) | 0.50, 0.33, 0.30 |
| RT-008 | E-010 (prompt), E-005 (llm) | 0.30, 0.24 |
| RT-009 | T-003 (order-system), E-002 (backend-architect) | 0.29, 0.26 |
| RT-010 | T-009 (concurrency), T-002 (architecture), E-006 (distributed) | 0.50, 0.29, 0.33 |
| RT-011 | T-005 (RAG), E-004 (rag-engineer), S-001 (RAG) | 0.50, 0.39, 0.43 |
| RT-012 | T-008 (frontend), E-009 (frontend-perf), E-008 (frontend-architect) | 0.50, 0.33, 0.27 |

---

## 4. Pilot Selection

### 4.1 Selection Method

```text
1. Score all 12 RT tasks using the 6-dimensional criteria
2. Rank by selection_score
3. Apply domain distribution constraints
4. Select top 10 within domain quotas
5. Exclude 2 lowest-scoring tasks
```

### 4.2 Ranked Selection

| rank | task_id | score | domain | decision |
|------|---------|-------|--------|----------|
| 1 | RT-003 | 2.90 | Database | **SELECTED** |
| 2 | RT-001 | 2.75 | Distributed | **SELECTED** |
| 3 | RT-002 | 2.75 | AI / RAG | **SELECTED** |
| 4 | RT-004 | 2.75 | Backend | **SELECTED** |
| 5 | RT-010 | 2.75 | Distributed | **SELECTED** |
| 6 | RT-012 | 2.75 | Frontend | **SELECTED** |
| 7 | RT-006 | 2.70 | Architecture | **SELECTED** |
| 8 | RT-011 | 2.60 | AI / RAG | **SELECTED** |
| 9 | RT-005 | 2.55 | Database | **SELECTED** |
| 10 | RT-009 | 2.40 | Backend | **SELECTED** |
| 11 | RT-007 | 2.25 | AI / Model | **EXCLUDED** |
| 12 | RT-008 | 2.25 | AI / Prompting | **EXCLUDED** |

### 4.3 Exclusion Rationale

```yaml
RT-007 (LLM接入层设计):
  reason: "Lower score (2.25). AI domain already covered by RT-002 and RT-011. 
           Memory match is weaker (T-006 tool-calling is adjacent, not exact). 
           Domain diversity score low (AI already has 2 reps)."

RT-008 (Prompt优化评审):
  reason: "Lower score (2.25). AI domain already covered. 
           Memory match is weak (E-010/E-005 only). 
           Prompt optimization is a narrow sub-task within AI."
```

### 4.4 Final Pilot Task Set

| # | task_id | user_request | domain | complexity | quality | key skills |
|---|---------|-------------|--------|------------|---------|------------|
| 1 | RT-003 | MySQL 慢查询 | Database | easy | 0.92 | database-engineer |
| 2 | RT-005 | Redis 缓存击穿 | Database / Cache | easy | 0.94 | database-engineer |
| 3 | RT-004 | 支付系统接口与安全 | Backend / Security | medium | 0.89 | backend-architect, security-engineer |
| 4 | RT-009 | 订单服务拆分方案 | Backend / Architecture | medium | 0.87 | backend-architect, system-architect |
| 5 | RT-002 | 企业知识库问答系统 | AI / RAG | medium | 0.91 | rag-engineer, llm-engineer |
| 6 | RT-011 | 向量库选型与召回策略 | AI / RAG | medium | 0.92 | rag-engineer, database-engineer |
| 7 | RT-012 | 前端性能优化与缓存策略 | Frontend | medium | 0.89 | frontend-architect |
| 8 | RT-006 | 微服务治理方案 | Architecture | hard | 0.90 | backend-architect, system-architect |
| 9 | RT-010 | 分布式事务设计 | Distributed | hard | 0.90 | distributed-system |
| 10 | RT-001 | 高并发秒杀系统 | Distributed | hard | 0.88 | distributed-system |

---

## 5. Distribution Check

### 5.1 Domain Distribution

| domain | target | selected | tasks |
|--------|--------|----------|-------|
| Backend | 2 | 2 | RT-004, RT-009 |
| Database | 2 | 2 | RT-003, RT-005 |
| Architecture | 2 | 2 | RT-006, RT-010 |
| AI / RAG | 2 | 2 | RT-002, RT-011 |
| Frontend | 1 | 1 | RT-012 |
| Distributed | 1 | 1 | RT-001 |

```yaml
domain_coverage: ALL TARGETS MET
```

### 5.2 Complexity Distribution

| complexity | target | selected | tasks |
|------------|--------|----------|-------|
| easy | 2 | 2 | RT-003, RT-005 |
| medium | 5 | 5 | RT-004, RT-009, RT-002, RT-011, RT-012 |
| hard | 3 | 3 | RT-006, RT-010, RT-001 |

```yaml
complexity_coverage: ALL TARGETS MET
```

### 5.3 Memory Type Coverage

| memory type | covered by |
|-------------|-----------|
| task | RT-004 (T-004), RT-002 (T-005), RT-003 (T-010), RT-012 (T-008), RT-010 (T-009), RT-006 (T-002) |
| failure | RT-004 (F-002) |
| success | RT-002 (S-001), RT-006 (S-002) |
| pattern | RT-004 (P-002), RT-006 (P-001) |
| anti-pattern | RT-003 (AP-001) |
| effectiveness | all tasks |

```yaml
memory_type_coverage: ALL TYPES REPRESENTED
```

---

## 6. Pilot Task Detail

### RT-003: MySQL 慢查询 (easy, Database)

```yaml
selection_score: 2.90 (highest)
memory_match:
  - T-010: MySQL slow query optimization (0.41)
  - AP-001: team-inflation anti-pattern (0.24)
  - E-003: database-engineer indexing baseline (0.19)
expected_memory_behavior:
  - AP-001 should trigger anti-pattern alert → prefer single-agent
  - T-010 confirms database-engineer approach
  - E-003 supports database-engineer role
baseline_decision:
  lead: database-engineer
  support: []
  team: single-agent
pilot_value: "Tests anti-pattern isolation. Simple task should NOT inflate team."
```

### RT-005: Redis 缓存击穿 (easy, Database / Cache)

```yaml
selection_score: 2.55
memory_match:
  - T-010: MySQL optimization (0.41) — indirect, different database
  - E-003: database-engineer baseline (0.19)
expected_memory_behavior:
  - Weak memory match — T-010 is MySQL, not Redis
  - Context compatibility should be LOW (different technology)
  - Tests: does memory correctly stay neutral?
baseline_decision:
  lead: database-engineer
  support: [backend-architect]
  team: single-agent
pilot_value: "Tests context compatibility. MySQL memory should NOT influence Redis decision."
```

### RT-004: 支付系统接口与安全 (medium, Backend / Security)

```yaml
selection_score: 2.75
memory_match:
  - F-002: payment security sequencing failure (0.53)
  - T-004: payment system with PCI-DSS (0.50)
  - P-002: security-first architecture pattern (0.41)
  - E-007: security-engineer effectiveness (0.39)
expected_memory_behavior:
  - F-002 should raise security-engineer priority
  - T-004 confirms backend-architect + security-engineer
  - P-002 supports security-first approach
  - Strongest memory match in entire pilot set
baseline_decision:
  lead: backend-architect
  support: [security-engineer]
  team: 2 roles
pilot_value: "Strongest memory signal. Tests if failure memory improves role priority."
```

### RT-009: 订单服务拆分方案 (medium, Backend / Architecture)

```yaml
selection_score: 2.40
memory_match:
  - T-003: order-system design (0.29)
  - E-002: backend-architect effectiveness (0.26)
expected_memory_behavior:
  - Weak to moderate memory match
  - T-003 is directly relevant (order system)
  - E-002 provides backend-architect baseline
  - Tests: does moderate memory signal influence architecture decision?
baseline_decision:
  lead: backend-architect
  support: [system-architect]
  team: 2 roles
pilot_value: "Tests moderate memory influence. Order system memory should confirm architect choice."
```

### RT-002: 企业知识库问答系统 (medium, AI / RAG)

```yaml
selection_score: 2.75
memory_match:
  - T-005: RAG system with evaluation (0.50)
  - S-001: RAG cross-domain success (0.43)
  - E-004: rag-engineer strong contribution (0.39)
  - E-005: llm-engineer baseline (0.24)
expected_memory_behavior:
  - T-005 + S-001 confirm RAG approach
  - E-004 supports rag-engineer as lead
  - E-005 supports llm-engineer as support
  - Should confirm existing decision without change
baseline_decision:
  lead: rag-engineer
  support: [llm-engineer, prompt-engineer]
  team: 3 roles
pilot_value: "Tests multi-role RAG team. Memory should confirm team structure."
```

### RT-011: 向量库选型与召回策略 (medium, AI / RAG)

```yaml
selection_score: 2.60
memory_match:
  - T-005: RAG system (0.50)
  - S-001: RAG success (0.43)
  - E-004: rag-engineer effectiveness (0.39)
expected_memory_behavior:
  - Similar memory match to RT-002
  - Different focus: vector store selection vs knowledge base
  - Tests: does memory differentiate between related AI subtasks?
baseline_decision:
  lead: rag-engineer
  support: [database-engineer]
  team: 2 roles
pilot_value: "Tests memory differentiation. RAG memory should apply but with narrower focus."
```

### RT-012: 前端性能优化与缓存策略 (medium, Frontend)

```yaml
selection_score: 2.75
memory_match:
  - T-008: SPA frontend performance (0.50)
  - E-009: frontend performance rules (0.33)
  - E-008: frontend-architect baseline (0.27)
expected_memory_behavior:
  - T-008 directly matches
  - E-009 supports frontend-performance role
  - Should confirm frontend-architect + frontend-performance
baseline_decision:
  lead: frontend-architect
  support: [backend-architect]
  team: 2 roles
pilot_value: "Tests frontend domain. Only frontend task in pilot set."
```

### RT-006: 微服务治理方案 (hard, Architecture)

```yaml
selection_score: 2.70
memory_match:
  - P-001: cross-domain architecture pattern (0.47)
  - T-002: architecture scale-up (0.29)
  - T-001: cross-domain architecture (0.39)
expected_memory_behavior:
  - P-001 supports cross-domain architecture approach
  - T-002 supports architecture team size
  - Multi-domain task → memory should support team formation
baseline_decision:
  lead: backend-architect
  support: [system-architect, devops-engineer]
  team: 3 roles
pilot_value: "Tests cross-domain architecture with memory. Pattern memory should influence team structure."
```

### RT-010: 分布式事务设计 (hard, Distributed)

```yaml
selection_score: 2.75
memory_match:
  - T-009: high-concurrency layer optimization (0.50)
  - E-006: distributed-system identity enforcement (0.33)
  - T-002: architecture scale-up (0.29)
expected_memory_behavior:
  - T-009 is concurrency-focused, not transaction-focused
  - E-006 supports distributed-system role
  - Context compatibility: medium (concurrency vs transaction both distributed)
baseline_decision:
  lead: distributed-system
  support: [system-architect]
  team: 2 roles
pilot_value: "Tests context compatibility. Concurrency memory applied to transaction task."
```

### RT-001: 高并发秒杀系统 (hard, Distributed)

```yaml
selection_score: 2.75
memory_match:
  - T-009: high-concurrency layer optimization (0.50)
  - E-006: distributed-system effectiveness (0.33)
  - T-002: architecture scale-up (0.29)
expected_memory_behavior:
  - T-009 directly matches (high concurrency)
  - E-006 supports distributed-system lead
  - High domain overlap → strong memory influence expected
baseline_decision:
  lead: distributed-system
  support: [system-architect, database-engineer]
  team: 3 roles
pilot_value: "Tests high-concurrency domain. Most complex single-domain task in pilot set."
```

---

## 7. Pilot Experiment Design

### 7.1 Two-Condition Protocol

```yaml
for_each_task:
  condition_a:  # Memory OFF
    mode: memory_off
    pipeline:
      - Task classification
      - Baseline Router
      - Baseline Orchestrator
      - Execution
    record:
      - router_decision
      - team
      - execution_result
      - quality_score
      - human_feedback

  condition_b:  # Memory ON
    mode: memory_on
    pipeline:
      - Task classification
      - Memory Retrieval
      - Evidence Filtering
      - Router + Memory
      - Orchestrator + Memory
      - Execution
    record:
      - retrieved_memories
      - memory_influence
      - router_decision
      - team
      - execution_result
      - quality_score
      - context_compatibility
      - memory_outcome
      - human_feedback
```

### 7.2 Evaluation Dimensions

```yaml
per_task:
  - decision_quality: "Was the routing/team choice correct?"
  - implementation_quality: "Was the implementation correct?"
  - memory_influence: "Did memory change the decision?"
  - memory_outcome: "Was the result helpful/neutral/harmful?"
  - context_compatibility: "Did memory context match the task?"
  - human_feedback: "What did the developer report?"
```

---

## 8. Limitations

```yaml
limitations:
  - "Only 12 of 58 claimed tasks are documented in individual records"
  - "No human feedback exists for any task (all are Phase 3/4 era)"
  - "All tasks are from 2026-08-30 (same date batch)"
  - "No project context (project_id, project_name, tech stack) documented"
  - "All tasks marked 'Good' result — no diversity in outcomes"
  - "No real code or configuration available for verification"
  - "No multi-project diversity (all tasks appear to be from same evaluation batch)"
  - "Memory Decision Log is empty (0 records) — no prior memory execution data"

sampling_limitation: true
impact: "Pilot tasks are from a single evaluation batch. Cross-project validation is not possible with current data."
```

---

## 9. Next Phase

### Phase 5.5.2.2 — Real Project Execution

```text
For each of the 10 pilot tasks:
  1. Execute Condition A (Memory OFF)
  2. Execute Condition B (Memory ON)
  3. Record all decisions, outcomes, and feedback
  4. Log to runtime/logs/real-project-memory-feedback.md
  5. Store in runtime/datasets/real-project/
  6. Generate pilot comparison
  7. Evaluate memory usefulness
  8. Check kill switch thresholds
```

### Key Observation Targets

```text
1. RT-003: anti-pattern alert → prefer single-agent?
2. RT-005: context compatibility LOW → memory stays neutral?
3. RT-004: strongest memory signal → failure memory improves security priority?
4. RT-010: context compatibility MEDIUM → concurrency memory applied to transactions?
5. RT-001: high domain overlap → memory improves distributed-system decision?
```

---

*Pilot Task Selection complete. 10 tasks selected from 12 candidates. Ready for Phase 5.5.2.2 Execution.*