# Phase 5.9.1 — Real Project Onboarding Report

**Date**: 2026-08-31
**Phase**: 5.9.1
**Status**: REAL_PROJECT_ONBOARDING: READY

---

## 1. Project Identity

```yaml
project_id: PROJ-001
project_name: "aiview — AI 面试陪练与智能反馈平台"
description: |
  全栈 AI 面试练习系统。AI 面试官实时问答，四维评分模型，
  知识图谱可视化，Dashboard 数据分析，RAG 知识库检索。
```

---

## 2. Repository

```yaml
repository_path: /home/shade/Public/test
repository_remote: origin/main
latest_commit: 56788e5 ("Web 应用")
git_history: 9 development phases (Phase 1-9)
```

### Git Log

```
56788e5 (HEAD -> main) Web 应用
3f8b6c8 Phase 8: 数据分析 Dashboard - 雷达图/趋势/薄弱点 + Redis 缓存
0ab4e4f Phase 7: 知识图谱 - 掌握度聚合 + ECharts 力导向图
63a1248 Phase 6: AI 评分 - 四维评分 + RabbitMQ 异步消费
23594d0 Phase 5: 面试状态机 - tool calling + Redis 分布式锁
410d809 Phase 4: AI 面试官流式输出 - SSE 打字机
27c1a9c Phase 3: AI 面试官基础版 - ChatClient + 问答循环
15c9d05 Phase 2: 登录/用户系统 - JWT 双 token
eea72a0 Phase 1: 项目初始化 - Docker Compose 骨架
```

---

## 3. Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Java | 21 |
| Framework | Spring Boot | 3.3.5 |
| ORM | MyBatis Plus | 3.5.9 |
| Database | MySQL | 8 |
| Cache | Redis (Redisson) | 7 (3.35.0) |
| MQ | RabbitMQ | 3 |
| Security | Spring Security + JWT | jjwt 0.12.6 |
| Frontend | Vue 3 + TypeScript + Vite | 3.5 / 5.7 / 6 |
| UI | Tailwind CSS | 4 |
| Charts | ECharts | 5.6 |
| AI | OpenAI Compatible (DeepSeek/OpenAI/Ollama) | - |
| Deployment | Docker Compose | - |

---

## 4. Architecture

```
Architecture: Monolith (Spring Boot)

Modules:
├── agent/ai       OpenAI Compatible ChatClient, Embedding, Tool calling
├── auth           JWT 双 token, Spring Security, 用户系统
├── interview      面试会话管理, 状态机, AI 评分, Dashboard
├── rag            知识库, 文本分块, 向量检索
└── common         异常处理, 统一响应, 用户上下文

Infrastructure:
├── mysql:8        aiview-mysql
├── redis:7-alpine aiview-redis
├── rabbitmq:3     aiview-rabbitmq
└── ollama         aiview-ollama (local models)
```

---

## 5. Modules

| Module | Description | Key Files |
|--------|------------|-----------|
| agent/ai | OpenAI Compatible 多供应商 ChatClient | OpenAiCompatibleChatClient.java, EmbeddingClient.java |
| auth | JWT 双 token 认证 + Spring Security | JwtUtil.java, AuthService.java, SecurityConfig.java |
| interview | 面试状态机, AI 评分, Dashboard | InterviewStateStore.java, InterviewScoringService.java, DashboardService.java |
| rag | 知识库管理, 文本分块, 向量检索 | RagService.java, KnowledgeBase.java, KnowledgeChunk.java |
| common | 全局异常处理, 统一响应 | GlobalExceptionHandler.java, Result.java |

---

## 6. Current Stage

```yaml
stage: active_development
current_phase: Phase 9 (Web 应用整体优化)
completed_phases: 8
total_commits: 9
```

---

## 7. Real Task Inventory

| Task ID | Description | Domain | Status |
|---------|------------|--------|--------|
| PROJ-001-T001 | RAG 知识库检索优化 | AI / RAG | pending |
| PROJ-001-T002 | 面试评分模型增强 | AI / Evaluation | pending |
| PROJ-001-T003 | Dashboard 性能优化 | Backend / Performance | pending |
| PROJ-001-T004 | 面试状态机可靠性增强 | Backend / Distributed | pending |
| PROJ-001-T005 | 用户认证安全增强 | Backend / Security | pending |

**5 tasks identified, all pending. None executed.**

---

## 8. Memory Compatibility

| Level | Memory | Reason |
|-------|--------|--------|
| High | T-001, T-002, T-003, T-004, E-001, S-001, P-001 | Spring Boot, 微服务, 架构设计, 通用技能 |
| Medium | T-005 (RAG), E-004, E-005 | aiview has RAG module, partial match |
| Low | E-002, E-003 | Limited direct applicability |

**T-005 (RAG)**: Medium compatibility. aiview has a RAG module with text chunking, embedding, and knowledge base retrieval. T-005's RAG system design patterns are partially applicable.

---

## 9. Privacy Audit

### Sensitive Fields Found

| Field | Location | Value Type | Risk |
|-------|----------|-----------|------|
| DEEPSEEK_API_KEY | .env, .env.example, application.yml | Placeholder (sk-xxxx) | Low |
| OPENAI_API_KEY | .env, .env.example, application.yml | Placeholder (sk-xxxx) | Low |
| JWT_SECRET | .env, .env.example, application.yml | Dev placeholder | Low |
| MYSQL_PASSWORD | docker-compose.yml, application-*.yml | Dev credential (aiview) | Low |
| MYSQL_ROOT_PASSWORD | docker-compose.yml | Dev credential (root) | Low |

### Privacy Verdict

**PASS** — All sensitive values are:
- Environment variable references (not hardcoded)
- Placeholder values (sk-xxxx)
- Local development credentials (not production)

**No real secrets, API keys, or production credentials found in the codebase.**

### Privacy Rules for Memory

```yaml
allowed_in_memory:
  - technology_stack
  - architecture_patterns
  - module_names
  - public_api_endpoints

forbidden_in_memory:
  - api_keys
  - passwords
  - tokens
  - secrets
  - private_keys
  - user_data
```

---

## 10. Execution Policy

```yaml
runtime:
  controller: loop_controller.py
  default_model: opencode/big-pickle
  fallback: big-pickle → nemotron-3.5-lightning-free

human_review:
  enabled: true
  required: true
  triggers: every_execution

evidence:
  first_observation: candidate
  second_observation: candidate
  then: validation → human_review → promotion
```

---

## 11. Evidence Policy

### Evidence Level Progression

```
benchmark_evaluated
  → runtime_validated          ✅ (Phase 5.8.2)
  → real_project_candidate      ⬜ (first real task execution)
  → human_review                ⬜
  → real_project_validated      ⬜
```

### First Evidence Rule

```
第一次观察: candidate
第二次独立观察: candidate
第三步: validation
然后: human review
最后: promotion

禁止: 第一次成功 → trusted memory
```

---

## 12. Human Review Policy

```yaml
required: true
minimum_reviewers: 1
reviewer_role: developer
review_items:
  - agent_output_correctness
  - memory_was_helpful
  - memory_caused_regression
  - decision_quality
  - code_quality
```

---

## 13. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| AI model produces incorrect code | Medium | Human review required |
| Memory context mismatch | Medium | Low relevance memories filtered |
| RAG tasks may not match T-005 well | Low | T-005 rated medium compatibility |
| First real project — no baseline | Low | Start with Memory OFF baseline |
| Task boundary too broad for agent | Medium | Task descriptions are scoped |

---

## 14. Readiness

```yaml
REAL_PROJECT_ONBOARDING: READY

acceptance_criteria:
  Real Project identified:        ✅  (aiview, /home/shade/Public/test)
  Repository verified:            ✅  (9 commits, git history)
  Technology Stack verified:      ✅  (Spring Boot 3.3, MySQL 8, Redis 7, Vue 3)
  Project Profile created:        ✅  (PROJ-001.yaml)
  >=3 Real Tasks identified:      ✅  (5 tasks)
  Memory Compatibility checked:   ✅  (high/medium/low mapped)
  Privacy Rules checked:          ✅  (no real secrets exposed)
  Human Review enabled:           ✅  (required every execution)
  Auto Promotion disabled:        ✅  (manual review only)
```

---

## 15. Files Created

| File | Path |
|------|------|
| Project Profile | runtime/datasets/real-project/projects/PROJ-001.yaml |
| Task Inventory | runtime/datasets/real-project/tasks/PROJ-001-tasks.yaml |
| Memory Policy | runtime/datasets/real-project/projects/PROJ-001-memory-policy.yaml |
| Execution Policy | runtime/datasets/real-project/projects/PROJ-001-execution-policy.md |
| Evidence Log | runtime/logs/real-project/PROJ-001.md |

---

## 16. Next Steps

```yaml
next_step: |
  Phase 5.9.1 is complete. The project is onboarded and ready.

  When ready to execute:
    1. Select a task from the inventory (e.g., PROJ-001-T001)
    2. Run Memory OFF baseline:
       python3 runtime/loop-controller/loop_controller.py \
         PROJ-001-T001 "RAG 知识库检索优化" disabled
    3. Run Memory ON:
       python3 runtime/loop-controller/loop_controller.py \
         PROJ-001-T001 "RAG 知识库检索优化" enabled
    4. Human review both outputs
    5. Record feedback in feedback/PROJ-001-T001-feedback.yaml
    6. Repeat for additional tasks to accumulate evidence

do_not:
  - Execute tasks without human review
  - Auto-promote memories
  - Modify project source code
  - Create new agents for the project
```

---

Generated: 2026-08-31
Phase: 5.9.1
Report: runtime/reports/phase-5.9.1-real-project-onboarding.md