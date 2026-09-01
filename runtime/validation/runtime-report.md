# Runtime Report — RV-2026-09-01-001
# Runtime Diagnosis of Interview Session Drift and Auth-State Corruption

## Executive Summary

Runtime diagnosis of 4 reported bugs in the AI Interview Platform (com.aiview) identified 5 root causes across 4 engineering domains. The bugs stem from: (1) Redis state expiry with stale DB rehydration, (2) non-idempotent answer submission, (3) non-idempotent scoring consumer with double-consumer registration, (4) missing token revocation, and (5) missing conditional property on InterviewScoringService.

All root causes are independently fixable. A 4-role team (backend-architect lead, database-engineer, distributed-system, security-engineer) with code-reviewer gate has been planned across 3 execution layers.

## Project Profile

| Attribute | Value |
|-----------|-------|
| Project | AI Interview Platform (com.aiview) |
| Backend | Java 21 / Spring Boot 3.3.5 / MyBatis-Plus |
| Persistence | MySQL + Redis (Redisson) |
| Messaging | RabbitMQ (direct exchange) |
| Auth | JWT + Spring Security (STATELESS) |
| Frontend | Vue 3 + Vite (out of scope) |
| Modules | auth, interview, agent, rag, common, config |

## Bug Summary

| Bug ID | Title | Severity | Root Cause | Fix Owner |
|--------|-------|----------|------------|-----------|
| BUG-001 | Session state rehydration from DB produces stale currentQuestionId | HIGH | InterviewStateStore Redis TTL expiry + DB fallback without validation | backend-architect |
| BUG-002 | Answer submission not idempotent — retries create duplicate rows | HIGH | No request-level idempotency key | backend-architect |
| BUG-003 | RabbitMQ scoring processed twice — duplicate InterviewResult rows | HIGH | No SELECT-before-INSERT idempotency check | distributed-system |
| BUG-004 | No token revocation — old refresh tokens valid for 7 days | MEDIUM | No revocation mechanism or token family tracking | security-engineer |
| BUG-005 | InterviewScoringService lacks @ConditionalOnProperty — double consumer | HIGH | Missing annotation causes both consumers active in rule mode | distributed-system |

## Root Cause Analysis

### BUG-001: Stale Session State Rehydration

**Flow:**
```
Client → InterviewService.answer() → InterviewStateStore.read(sessionId)
  → Redis MISS → DB fallback → InterviewSession from DB
  → currentQuestionId from DB may not match actual last-asked question
  → requireAsking() accepts stale state → wrong question set exposed
```

**Evidence:**
- `InterviewStateStore.java`: Redis key TTL is 24 hours. On miss, reads from `InterviewSessionMapper.selectById()`.
- `InterviewService.java:requireAsking()`: Checks `status == ASKING || status == START` but does NOT validate `currentQuestionId` against message history.
- `InterviewSession` entity stores `currentQuestionId` as a single field — if state diverged (e.g., concurrent operation), this field may be stale.

### BUG-002: Non-Idempotent Answer Submission

**Flow:**
```
Client → POST /api/interviews/{id}/answer (retry after timeout)
  → InterviewService.answer() → lockFor(sessionId)
  → InterviewMessage inserted (duplicate content)
  → questionCount incremented (now wrong)
  → askedQuestionIds now includes duplicate question
  → Next question selection may change
```

**Evidence:**
- `InterviewService.answer()`: No idempotency key check. Each call inserts a new `InterviewMessage` row.
- `QuestionBank.pickQuestion()`: Uses `excludeIds` from message history — duplicate answers change the exclusion set.
- No request deduplication mechanism exists anywhere in the codebase.

### BUG-003+BUG-005: Double Consumer + Non-Idempotent Scoring

**Flow:**
```
InterviewService.finishSession()
  → rabbitTemplate.convertAndSend(SCORING_EXCHANGE, ScoringMessage)
  → Queue: aiview.interview.scoring
  → Consumer 1: RuleBasedScoringService (@ConditionalOnProperty mode=rule) ✅ active
  → Consumer 2: InterviewScoringService (NO @ConditionalOnProperty) ✅ active
  → Both process the same message
  → Both call resultMapper.insert(result)
  → Duplicate InterviewResult rows in DB
```

**Evidence:**
- `InterviewScoringService.java`: Has `@RabbitListener` but NO `@ConditionalOnProperty` — always registered as a Spring bean.
- `RuleBasedScoringService.java`: Has `@ConditionalOnProperty(name="app.interview.mode", havingValue="rule", matchIfMissing=true)` — active in default mode.
- Both listen on the same queue `aiview.interview.scoring`.
- `resultMapper.insert(result)` is unconditional — no check for existing result.

### BUG-004: No Token Revocation

**Flow:**
```
Client → POST /api/auth/refresh (with valid refresh token)
  → AuthService.refresh() → jwtUtil.parse(refreshToken) → OK
  → buildAuthResponse(user) → new access token + new refresh token
  → Old refresh token NOT revoked
  → Attacker who stole old token can still use it
  → Each use generates another valid refresh token (token chain)
```

**Evidence:**
- `AuthService.refresh()`: Issues new tokens but does not invalidate old ones.
- No Redis-based revocation list exists.
- No token family ID or jti claim for tracking.
- `JwtAuthenticationFilter`: Does not check any revocation list.

## Team Plan Summary

| Layer | Task Cards | Roles | Dependencies |
|-------|-----------|-------|-------------|
| Layer 1 | TC-001, TC-002, TC-003, TC-004 | backend-architect, database-engineer, distributed-system, security-engineer | None (parallel) |
| Layer 2 | TC-005 | backend-architect | TC-001, TC-002, TC-003 |
| Layer 3 | TC-006 | code-reviewer | TC-001 through TC-005 |

## Files Explored

| Module | Files | Key Classes |
|--------|-------|-------------|
| auth | 13 | JwtUtil, JwtAuthenticationFilter, AuthUser, AuthService, UserContext, SecurityConfig |
| interview | 31 | InterviewService, InterviewStateStore, QuestionBank, EvaluationService, RuleBasedScoringService, InterviewScoringService |
| agent | 12 | ChatClient, OpenAiCompatibleChatClient, EmbeddingClient, AiProperties |
| common + config | 12 | BizException, ResultCode, UserContext, SecurityConfig, RedissonConfig, RabbitConfig, MybatisPlusConfig |
| **Total** | **68** | |

## Evidence Files

| File | Purpose |
|------|---------|
| `~/.agents/runtime/validation/execution-trace.yaml` | Full execution trace with timestamps |
| `~/.agents/runtime/validation/team-plan.yaml` | Team composition and layered execution plan |
| `~/.agents/runtime/validation/task-cards.yaml` | 6 task cards with quality criteria |
| `~/.agents/runtime/validation/memory-impact.md` | Memory recall results and proposed updates |
| `~/.agents/runtime/validation/runtime-report.md` | This file — executive summary |

## Status

| Phase | Status |
|-------|--------|
| Intent Classification | ✅ Complete |
| Domain Classification | ✅ Complete (4 domains: backend, database, distributed, security) |
| Memory Recall | ✅ Complete (0 matches — first-time project) |
| Skill Routing | ✅ Complete (backend-architect lead, 4 support) |
| Codebase Exploration | ✅ Complete (68 files across 4 modules) |
| Root Cause Analysis | ✅ Complete (5 root causes identified) |
| Team Plan | ✅ Complete (3 layers, 6 task cards) |
| Human Review Gate | ⏳ Pending approval |
| Delegation | ⏳ Pending approval |
| Execution | ⏳ Pending approval |
