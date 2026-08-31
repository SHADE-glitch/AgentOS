# Phase 5.9.3 — PROJ-001 No-AI Rebuild Architecture Audit

**Date**: 2026-08-31
**Phase**: 5.9.3
**Project**: PROJ-001 (aiview)
**Status**: READ ONLY — Audit Complete
**Evidence**: 60+ files read, 100% code coverage of all modules

---

## CURRENT ARCHITECTURE

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                       │
│  Home │ Interview │ Dashboard │ KnowledgeMap │ Auth      │
│  ────────┼──────────────┼──────────────┼─────────────── │
│         │   SSE Stream  │    REST API   │                │
└─────────┼──────────────┼──────────────┼─────────────────┘
          │              │              │
┌─────────┼──────────────┼──────────────┼─────────────────┐
│         ▼              ▼              ▼                  │
│              Backend (Spring Boot 3.3.5)                  │
│                                                           │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  auth/   │  │  interview/  │  │     rag/         │   │
│  │  (JWT)   │  │  (session,   │  │  (knowledge base,│   │
│  │          │  │   message,    │  │   chunk, vector  │   │
│  │          │  │   result,     │  │   search)        │   │
│  │          │  │   dashboard,  │  │         │        │   │
│  │          │  │   knowledge   │  │         ▼        │   │
│  │          │  │   map)        │  │  ┌──────────────┐│   │
│  │          │  │      │        │  │  │  agent/ai/   ││   │
│  │          │  │      ▼        │  │  │  ChatClient  ││   │
│  │          │  │  ┌──────────┐ │  │  │  Embedding   ││   │
│  │          │  │  │ agent/ai/│◄┼──┼──┤  Client      ││   │
│  │          │  │  │ ChatClient│ │  │  └──────┬───────┘│   │
│  │          │  │  └──────────┘ │  │         │         │   │
│  └──────────┘  └──────────────┘  └─────────┼─────────┘   │
│                                             │             │
└─────────────────────────────────────────────┼─────────────┘
                                              │
                    ┌─────────────────────────┼─────────┐
                    │          Ollama          │         │
                    │   qwen2.5:3b             │         │
                    │   nomic-embed-text       │         │
                    └───────────────────────────┘         │
                                                          │
  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
  │  MySQL 8 │  │ Redis 7  │  │RabbitMQ 3│               │
  └──────────┘  └──────────┘  └──────────┘               │
```

### Backend Modules

| Module | Classes | Classification | AI Dependency |
|--------|---------|----------------|---------------|
| `agent/ai/` | 9 | AI | **Fully AI** — ChatClient, EmbeddingClient, OpenAiCompat clients |
| `auth/` | 10 | CORE_BUSINESS | None |
| `common/` | 6 | INFRASTRUCTURE | None |
| `config/` | 6 | INFRASTRUCTURE | Partially (AiProperties) |
| `interview/` | 18 | CORE_BUSINESS | Partially (InterviewService, InterviewScoringService) |
| `rag/` | 7 | AI | **Fully AI** — vector embedding, cosine search, knowledge base CRUD |

### Infrastructure Services

| Service | Purpose | AI-Related | After Rebuild |
|---------|---------|------------|----------------|
| MySQL 8 | Primary database | No | KEEP |
| Redis 7 | Session state, cache, locks | No | KEEP |
| RabbitMQ 3 | Async scoring queue | Partially | CONDITIONAL |
| **Ollama** | Local LLM (chat + embedding) | **Yes** | REMOVE |
| Backend | Spring Boot app | Partially | KEEP (refactored) |
| Frontend | Vue 3 SPA | Partially | KEEP (refactored) |

---

## AI DEPENDENCY MAP

```
Ollama (Docker)
  │
  ├──► OpenAiCompatibleChatClient ──► ChatClient (interface)
  │       │                              │
  │       ├──► InterviewService ──► question generation
  │       │       │                    follow-up questions
  │       │       │                    RAG context injection
  │       │       │                    streaming responses
  │       │       │
  │       │       └──► InterviewScoringService ──► LLM scoring
  │       │              (via RabbitMQ)
  │       │
  │       └──► (standalone use)
  │
  └──► OpenAiCompatibleEmbeddingClient ──► EmbeddingClient (interface)
          │
          └──► RagService ──► vector search
                  │            cosine similarity
                  │            knowledge chunk CRUD
                  │
                  └──► InterviewService ──► retrieveRagContext()
```

### AI Code Inventory

| File | AI Dependency | Evidence |
|------|--------------|----------|
| `agent/ai/ChatClient.java` | Interface | `chat(ChatRequest)`, `chatStream()` |
| `agent/ai/EmbeddingClient.java` | Interface | `embed()`, `embedAll()` |
| `agent/ai/OpenAiCompatibleChatClient.java` | Implementation | REST calls to AI provider |
| `agent/ai/OpenAiCompatibleEmbeddingClient.java` | Implementation | REST calls to embedding API |
| `agent/ai/ChatMessage.java` | Model | system/user/assistant roles |
| `agent/ai/ChatRequest.java` | Model | model, temperature, tools |
| `agent/ai/ChatTool.java` | Model | tool calling definition |
| `agent/ai/ToolCall.java` | Model | tool call response |
| `rag/service/RagService.java` | Service | `embeddingClient.embed()`, `cosine()` |
| `rag/controller/RagController.java` | Controller | All endpoints are RAG |
| `rag/entity/KnowledgeBase.java` | Entity | RAG-only data |
| `rag/entity/KnowledgeChunk.java` | Entity | `embedding` column (JSON vector) |
| `config/AiProperties.java` | Config | DeepSeek/OpenAI/Ollama config |
| `interview/InterviewService.java` | Service | `chatClient.chatStreamTools()`, `ragService.retrieveRagContext()` |
| `interview/InterviewScoringService.java` | Service | `chatClient.chat()` for LLM scoring |
| `ollama/` | Infrastructure | Dockerfile for local LLM |

---

## CORE BUSINESS (No-AI)

### What Remains After AI Removal

```
User
 ├── Authentication (JWT login/register)
 ├── Interview Sessions
 │    ├── Topic selection (from knowledge_point)
 │    ├── Question display (from question bank)
 │    ├── Answer submission
 │    ├── Self-evaluation or rule-based scoring
 │    └── Result viewing
 ├── Dashboard
 │    ├── Radar chart (4 dimensions)
 │    ├── Score trend
 │    ├── Weak points
 │    └── Suggestions
 └── Knowledge Map
      └── Topic mastery visualization
```

### Domain Entities (Post-AI)

| Entity | Table | Action | Notes |
|--------|-------|--------|-------|
| User | `app_user` | KEEP | |
| UserProfile | `user_profile` | KEEP | |
| KnowledgePoint | `knowledge_point` | KEEP | Question bank hierarchy (seed data) |
| Question | `question` | KEEP | Remove `source='AI'` rows |
| InterviewSession | `interview_session` | KEEP | |
| InterviewMessage | `interview_message` | KEEP | Role column preserved |
| InterviewResult | `interview_result` | KEEP | |
| KnowledgeBase | `knowledge_base` | **REMOVE** | |
| KnowledgeChunk | `knowledge_chunk` | **REMOVE** | |

### Product Redefinition

```yaml
CURRENT: "AI 面试陪练与智能反馈平台"
PROPOSED: "面试训练平台"

TARGET_USER: 技术面试备考者
CORE_PROBLEM: 需要系统化、可追踪的面试练习
CORE_WORKFLOW:
  1. 选择主题 + 难度
  2. 系统从题库出题
  3. 用户作答
  4. 结构化自评或规则评分
  5. Dashboard 追踪进度
```

---

## REMOVE / KEEP / REFACTOR / NEW

### REMOVE (Entire modules/files)

```
backend/src/main/java/com/aiview/agent/          # 9 files
backend/src/main/java/com/aiview/rag/             # 7 files
backend/.../config/AiProperties.java              # 1 file
ollama/                                           # 1 directory
knowledge_base table                               # DB
knowledge_chunk table                              # DB
app.ai section in application.yml                  # Config
```

### KEEP (As-is)

```
auth/                                              # 10 files (entire module)
common/                                            # 6 files (entire module)
config/SecurityConfig.java                         # 1 file
config/MybatisPlusConfig.java                      # 1 file
config/MybatisMetaHandler.java                     # 1 file
interview/entity/*                                 # 4 files
interview/mapper/*                                 # 4 files
interview/dto/*                                    # 7 files
interview/service/DashboardService.java            # 1 file
interview/service/KnowledgeMapService.java         # 1 file
interview/service/InterviewStateStore.java         # 1 file
interview/controller/DashboardController.java      # 1 file
interview/controller/KnowledgeController.java      # 1 file
frontend/pages/Dashboard.vue                       # 1 file
frontend/pages/KnowledgeMap.vue                    # 1 file
frontend/pages/Login.vue                           # 1 file
frontend/pages/Register.vue                        # 1 file
frontend/api/auth.ts                               # 1 file
frontend/api/client.ts                             # 1 file
frontend/api/dashboard.ts                          # 1 file
frontend/stores/auth.ts                            # 1 file
```

### REFACTOR (Rewrite with same interface)

```
interview/service/InterviewService.java            # Remove AI, add question bank
interview/service/InterviewScoringService.java     # Replace AI with self-eval/rule-based
interview/controller/InterviewController.java      # Remove streaming endpoint
frontend/pages/Interview.vue                       # Remove SSE, add question bank UI
frontend/pages/Home.vue                            # Remove AI branding
frontend/api/interview.ts                          # Remove streamAnswer
```

### NEW (Create)

```
Question bank management (admin CRUD)
Self-evaluation form (4 dimensions, 1-10 scale)
Question selection algorithm (by topic, difficulty)
```

---

## API Audit Summary

| Endpoint | AI Dependency | Action |
|----------|--------------|--------|
| `POST /api/auth/register` | None | KEEP |
| `POST /api/auth/login` | None | KEEP |
| `POST /api/auth/refresh` | None | KEEP |
| `GET /api/auth/me` | None | KEEP |
| `GET /api/health` | None | KEEP |
| `GET /api/topics` | None | KEEP |
| `POST /api/interviews` | Required | REFACTOR |
| `GET /api/interviews` | None | KEEP |
| `GET /api/interviews/{id}` | None | KEEP |
| `GET /api/interviews/{id}/result` | None | KEEP |
| `POST /api/interviews/{id}/answer` | Required | REFACTOR |
| `POST /api/interviews/{id}/answer/stream` | Required | REFACTOR |
| `GET /api/knowledge/map` | None | KEEP |
| `GET /api/dashboard` | None | KEEP |
| `GET /api/knowledge-bases` | Required | **REMOVE** |
| `POST /api/knowledge-bases` | Required | **REMOVE** |
| `DELETE /api/knowledge-bases/{id}` | Required | **REMOVE** |
| `GET /api/knowledge-bases/{id}/chunks` | Required | **REMOVE** |
| `POST /api/knowledge-bases/{id}/chunks` | Required | **REMOVE** |
| `DELETE /api/knowledge-bases/{id}/chunks/{chunkId}` | Required | **REMOVE** |
| `POST /api/knowledge-bases/search` | Required | **REMOVE** |

**Summary**: 14 KEEP, 4 REFACTOR, 7 REMOVE

---

## DATABASE AUDIT

### Tables to REMOVE

```sql
DROP TABLE IF EXISTS knowledge_chunk;  -- embedding vectors, AI-only
DROP TABLE IF EXISTS knowledge_base;   -- RAG knowledge bases, AI-only
```

### Data to Clean

```sql
DELETE FROM question WHERE source = 'AI';  -- AI-generated questions
```

### Tables to KEEP (unchanged schema)

```sql
app_user, user_profile, knowledge_point, question,
interview_session, interview_message, interview_result
```

---

## TECHNICAL DEBT

| # | Issue | Category | Severity | Rebuild Impact |
|---|-------|----------|----------|----------------|
| 1 | No test coverage (backend + frontend) | TEST | HIGH | Must add tests |
| 2 | F-001: O(n) chunk scan | CODE | MEDIUM | Removed with RAG |
| 3 | F-002: JSON embedding storage | DATA | MEDIUM | Removed with RAG |
| 4 | F-003: inSql concatenation (fixed) | SECURITY | LOW | Removed with RAG |
| 5 | F-004: No kb_id filter | CODE | LOW | Removed with RAG |
| 6 | F-005: No embedding cache | CODE | LOW | Removed with RAG |
| 7 | AI state machine in Redis | ARCHITECTURE | LOW | Simplify |
| 8 | No API versioning | ARCHITECTURE | MEDIUM | Add `/api/v1/` |
| 9 | Hardcoded AI provider config | DEPLOYMENT | LOW | Removed with AI |

---

## REBUILD STRATEGY

### Recommendation: Option A — Incremental Refactor

| Criteria | Option A | Option B | Option C |
|----------|----------|----------|----------|
| Cost | MEDIUM | MEDIUM | HIGH |
| Risk | LOW | MEDIUM | HIGH |
| Code Reuse | HIGH | MEDIUM | LOW |
| Data Migration | Easy | Medium | Hard |
| Testing | Add after refactor | New tests | From scratch |

**Reason**: AI dependency is well-isolated in `agent/ai/` and `rag/` modules. These can be cleanly removed. InterviewService needs refactoring but core entities are reusable. Auth/Common are completely AI-free.

### Rebuild Phases

```
Phase 0: Architecture Freeze        ← CURRENT
Phase 1: AI Removal                 (low risk, mechanical)
Phase 2: Domain Simplification      (medium risk, InterviewService refactor)
Phase 3: Backend Polish             (low risk, cleanup)
Phase 4: Frontend Refactor          (medium risk, Interview.vue rewrite)
Phase 5: Database Cleanup           (low risk, drop tables)
Phase 6: Testing                    (add tests)
Phase 7: Docker/Deployment          (remove Ollama, update compose)
```

---

## RISKS

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Question bank is empty (no seed questions) | **HIGH** | Seed question table before Phase 2 |
| 2 | Scoring replacement unclear (self-eval vs rule-based) | **HIGH** | Design decision in Phase 0 |
| 3 | Interview state machine designed for AI flow | MEDIUM | Simplify states for question bank |
| 4 | Redis dependency for InterviewStateStore | MEDIUM | Keep Redis (already in infra) |
| 5 | Interview.vue SSE refactoring is complex | MEDIUM | Redesign for question bank flow |

---

## EVIDENCE LEVEL

All conclusions are based on concrete code evidence:

```yaml
FACT:    60+ source files read and analyzed
FACT:    9 database tables mapped
FACT:    21 API endpoints audited
FACT:    6 frontend pages analyzed
FACT:    6 infrastructure services identified
FACT:    9 technical debt items documented

INFERENCE:  Product redefinition (面试训练平台)
INFERENCE:  Scoring approach (self-evaluation as default)
INFERENCE:  RabbitMQ conditional keep

RECOMMENDATION:  Incremental Refactor (Option A)
RECOMMENDATION:  Phase 0 → Phase 1 → Phase 2 → ...
```

---

## NEXT PHASE

```text
Phase 0: Architecture Freeze
```

**Actions needed from human reviewer**:
1. Review KEEP/REMOVE/REWRITE map
2. Decide scoring approach: self-evaluation vs rule-based vs rubric-based
3. Decide on RabbitMQ: keep or remove
4. Approve product redefinition: "面试训练平台"
5. Create rebuild git branch

---

## DATA FILES

| File | Path |
|------|------|
| Architecture Data (YAML) | [PROJ-001-no-ai-architecture.yaml](file:///home/shade/.agents/runtime/datasets/real-project/projects/PROJ-001-no-ai-architecture.yaml) |
| This Report | [phase-5.9.3-PROJ-001-no-ai-architecture-audit.md](file:///home/shade/.agents/runtime/reports/phase-5.9.3-PROJ-001-no-ai-architecture-audit.md) |

---

Generated: 2026-08-31
Phase: 5.9.3
Status: Audit Complete — Awaiting Human Review