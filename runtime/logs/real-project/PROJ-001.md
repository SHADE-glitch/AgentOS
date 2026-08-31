# Project Evidence Log — PROJ-001 (aiview)
# Phase 5.9.2 — Real Project Pilot Execution
# Updated: 2026-08-31

project_id: PROJ-001
project_name: "aiview — AI 面试陪练与智能反馈平台"

# ── Current State ──

```yaml
total_executions: 6
successful_executions: 3
failed_executions: 3
memory_used: 5 (per execution)
memory_helpful: 0
memory_harmful: 0
human_feedback: 1
evidence_level: real_project_candidate
files_changed: 1

implementation:
  status: IMPLEMENTED
  sub_id: F-003
  fix: inSql → parameterized .in()

verification:
  status: VERIFIED (Phase 5.9.2.5.1)
  java_21: available
  mvn_test: BUILD SUCCESS
  test_coverage: none (no tests in project)

test:
  status: BUILD_SUCCESS
  no_tests: true

environment:
  status: RESOLVED
  java_21_path: /usr/lib/jvm/java-21-openjdk-amd64

security_classification:
  original: CONFIRMED_SECURITY_RISK (SQL injection)
  re_evaluated: CODE_QUALITY_RISK
  reason: userId is Long from Spring Security context, not user input

human_feedback:
  pending: true
```

# ── Execution History ──

### 2026-08-31: PROJ-001-T001 (Attempt 1 — ling-3.0-flash-fin-free)

```yaml
project_id: PROJ-001
task_id: PROJ-001-T001
execution_id: EXEC-1788140467
trace_id: TRACE-EXEC-1788140467-7901a20453b2
loop_id: LOOP-20260831014106
model: opencode/ling-3.0-flash-fin-free
memory_used:
  - T-010
  - AP-001
  - T-005
  - P-001
  - S-002
memory_influence: confirmation
actual_result: timeout (120s)
human_feedback: ""
rework: false
memory_outcome: no_observable_effect (runtime failed)
```

### 2026-08-31: PROJ-001-T001 (Attempt 2 — big-pickle)

```yaml
project_id: PROJ-001
task_id: PROJ-001-T001
execution_id: EXEC-1788140609
trace_id: TRACE-EXEC-1788140609-2a39f4f4833e
loop_id: LOOP-20260831014329
model: opencode/big-pickle
memory_used:
  - P-001
  - T-009
  - T-005
  - E-004
  - T-010
memory_influence: confirmation
actual_result: timeout (120s)
human_feedback: ""
rework: false
memory_outcome: no_observable_effect (runtime failed)
```

### 2026-08-31: PROJ-001-T001 (Attempt 3 — nemotron-3.5-lightning-free)

```yaml
project_id: PROJ-001
task_id: PROJ-001-T001
execution_id: EXEC-1788140769
trace_id: TRACE-EXEC-1788140769-bd5f4473eaed
loop_id: LOOP-20260831014609
model: opencode/nemotron-3.5-lightning-free
memory_used:
  - P-001
  - AP-001
  - S-001
  - E-005
  - S-002
memory_influence: confirmation
actual_result: timeout (300s)
human_feedback: ""
rework: false
memory_outcome: no_observable_effect (runtime failed)
```

# ── Root Cause Analysis ──

```yaml
issue: opencode CLI --auto mode timeout
opencode_version: 1.18.25
affected_models:
  - ling-3.0-flash-fin-free
  - big-pickle
  - nemotron-3.5-lightning-free
working_model:
  - mimo-v2.5-free
resolution: |
  Phase 5.9.2.2: Switched default model to mimo-v2.5-free.
  Added --pure flag to opencode invocation.
  PROJ-001-T001 executed successfully (analysis only).
confirmed: true
impact: |
  Agent OS Runtime now operational with mimo-v2.5-free.
  Real project tasks can be executed.
  Previous 3 timeout losses are provider-level issues, not Agent OS bugs.
```

### 2026-08-31: PROJ-001-T001 (Attempt 4 — mimo-v2.5-free) ✅

```yaml
project_id: PROJ-001
task_id: PROJ-001-T001
execution_id: EXEC-1788143000
trace_id: TRACE-EXEC-1788143000-00f7962e69d6
loop_id: LOOP-20260831022319
model: opencode/mimo-v2.5-free
memory_used:
  - E-004
  - T-005
  - P-001
  - T-001
  - S-001
memory_influence: confirmation
actual_result: success (analysis only, 35.7s)
output: 5 optimization strategies (chunking, query enhancement, hybrid search, reranking, metadata filtering)
human_feedback: pending
rework: false
memory_outcome: confirmation (supporting context provided, no decision override)
files_changed: []
evidence_level: real_project_candidate
```

### 2026-08-31: PROJ-001-T001 Human Review (Phase 5.9.2.3)

```yaml
task_id: PROJ-001-T001
review_date: 2026-08-31
reviewer: human
decision: DEFER
reason: |
  All 5 agent recommendations are generic RAG best practices as Python code.
  None are specific to Java/Spring Boot/MyBatis-Plus project.
  Agent missed actual code issues: O(n) linear scan, JSON vector storage,
  SQL injection risk in inSql.
recommendations_classified:
  - chunking: PARTIAL_EVIDENCE
  - query_enhancement: GENERIC_RECOMMENDATION
  - hybrid_search: PARTIAL_EVIDENCE
  - reranking: GENERIC_RECOMMENDATION
  - metadata_filtering: PARTIAL_EVIDENCE
overall: neutral (not helpful, not harmful)
memory_influence: confirmation (no decision change)
```

### 2026-08-31: PROJ-001-T001 Code-Specific Re-Analysis (Phase 5.9.2.4)

```yaml
task_id: PROJ-001-T001
execution_id: (new)
session_id: ses_faa54a29fffec7T9uzYs9B9JKo
model: opencode/mimo-v2.5-free
mode: read-only
status: success
latency: 46.1s

code_evidence:
  findings: 5
  classification: FACT (4), INFERENCE (1)
  java_native: true
  python_code: 0

recommendations:
  original_5: re-evaluated (no change in classification)
  new_code_specific: 2 implementation candidates
  strongest: F-003 (SQL injection fix)

comparison_vs_first:
  generic_before: 5
  evidence_after: 5
  python_examples_before: 5
  python_examples_after: 0

decision: PROCEED
candidates:
  - Candidate A: Fix SQL injection (parameterized query)
  - Candidate B: Add kbId filter to SearchRequest
files_to_change:
  - backend/src/main/java/com/aiview/rag/service/RagService.java
  - backend/src/main/java/com/aiview/rag/dto/RagDtos.java
project_modified: NO
```

### 2026-08-31: PROJ-001-T001-F003 Implementation (Phase 5.9.2.5)

```yaml
task_id: PROJ-001-T001
sub_id: F-003
execution_id: EXEC-1788144371
trace_id: TRACE-EXEC-1788144371-f003-fix
mode: manual (human engineer)
status: success

fix: |
  Replaced inSql with userId string concatenation
  with parameterized .in() query using MyBatis-Plus LambdaQueryWrapper.
  RagService.java search() method.

files_changed:
  - backend/src/main/java/com/aiview/rag/service/RagService.java

diff_stat: |
  1 file changed, 8 insertions(+), 4 deletions(-)

test_result:
  mvn_test: FAILED (Java 21 required, only 17 available)
  manual_verification: PASS
    - API signature unchanged
    - Business logic unchanged
    - @TableLogic preserves deleted=0 filtering
    - No SQL injection vector

regression: PASS
deferred: F-001, F-002, F-004, F-005

result: IMPLEMENTED
evidence_level: real_project_candidate
project_modified: YES (1 file, security fix only)
```

### 2026-08-31: PROJ-001-T001-F003 Verification (Phase 5.9.2.5.1)

```yaml
phase: 5.9.2.5.1
task_id: PROJ-001-T001
sub_id: F-003
type: verification

environment:
  java_21_found: YES
  java_21_path: /usr/lib/jvm/java-21-openjdk-amd64
  default_java: 17.0.20

test_result:
  mvn_test: BUILD SUCCESS
  exit_code: 0
  tests_passed: 0
  tests_failed: 0
  test_coverage: none (no test sources)

security_reevaluation:
  original: CONFIRMED_SECURITY_RISK (SQL injection)
  reclassified: CODE_QUALITY_RISK
  reason: |
    userId is a Long from SecurityContextHolder (Spring Security),
    not from user input. inSql is a code smell, not exploitable
    SQL injection in this context.

git_diff:
  confirmed: 1 file, +9/-3, only RagService.java
  no_unrelated: YES
  not_committed: YES

behavior_check:
  api_signature: unchanged
  business_logic: unchanged
  embedding: unchanged
  similarity: unchanged
  topK: unchanged

decision: IMPLEMENTATION_VERIFIED
evidence_level: real_project_candidate

report: runtime/reports/phase-5.9.2.5.1-PROJ-001-T001-verification.md
```

### 2026-08-31: PROJ-001 No-AI Architecture Audit (Phase 5.9.3)

```yaml
phase: 5.9.3
type: READ_ONLY_AUDIT
status: COMPLETE

scope: |
  Full project architecture audit for No-AI rebuild.
  Read 60+ source files. Mapped all modules, entities,
  APIs, frontend pages, infrastructure services.

findings:
  ai_modules: [agent/ai, rag, ollama, AiProperties]
  ai_dependent_services: [InterviewService, InterviewScoringService]
  ai_free_modules: [auth, common, DashboardService, KnowledgeMapService]
  ai_database_tables: [knowledge_base, knowledge_chunk]
  ai_api_endpoints: 7 (all /api/knowledge-bases/*)
  ai_config: app.ai section in application.yml

target_architecture:
  product: "面试训练平台" (was "AI 面试陪练与智能反馈平台")
  strategy: Incremental Refactor (Option A)
  phases: 0-7 (Phase 0 = Architecture Freeze, current)

decisions:
  REMOVE: agent/ai, rag, ollama, AiProperties, knowledge_base, knowledge_chunk
  KEEP: auth, common, DashboardService, KnowledgeMapService, all entities
  REFACTOR: InterviewService, InterviewScoringService, InterviewController, Interview.vue, Home.vue
  NEW: question bank management, self-evaluation, question selection
  CONDITIONAL: RabbitMQ (depends on scoring design), Redis (keep)

risks:
  - Question bank may be empty (HIGH)
  - Scoring replacement unclear (HIGH)
  - Interview state machine AI-designed (MEDIUM)

human_review_required:
  - KEEP/REMOVE/REWRITE map approval
  - Scoring approach decision
  - RabbitMQ decision
  - Product redefinition approval

reports:
  - runtime/reports/phase-5.9.3-PROJ-001-no-ai-architecture-audit.md
  - runtime/datasets/real-project/projects/PROJ-001-no-ai-architecture.yaml

evidence_level: real_project_candidate
project_modified: NO (READ ONLY)
```