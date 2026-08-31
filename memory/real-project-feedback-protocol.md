# Real Project Feedback Protocol

## 1. Purpose

This protocol defines how real engineering project tasks feed back into the Engineering Memory system, establishing a closed loop from task execution through memory retrieval to outcome evaluation.

```text
Real Project
  ↓
Task
  ↓
Memory Retrieval
  ↓
Decision
  ↓
Implementation
  ↓
Result
  ↓
Human / Developer Feedback
  ↓
Memory Evaluation (helpful | neutral | harmful)
  ↓
New Insight / Observation
```

---

## 2. What Qualifies as a Real Project

A real project must satisfy ALL of:

```yaml
real_project_criteria:
  - genuine project context (not synthetic for testing)
  - real engineering problem (not fabricated)
  - real code / configuration / architecture
  - real development decision
  - real implementation result
  - human review or developer feedback available
```

Examples of valid real projects:

```text
Java Spring Boot backend
Database optimization task
Redis cache architecture
AI / RAG application
Frontend SPA optimization
Distributed system design
Security audit
Performance tuning
```

---

## 3. Anti-Fabrication Rule

```text
DO NOT create a fake project just to test Memory.
DO NOT fabricate feedback to make metrics look good.
DO NOT mark a benchmark task as a real project.

If no real project data exists, record:
  real_project_evidence: insufficient
  status: PROVISIONAL

The credibility of the Agent OS is more important than any benchmark score.
```

---

## 4. Project Event Schema

Every real project task that involves Memory Retrieval must record:

```yaml
project_event:
  project_id: "<uuid>"
  project_name: "<name>"
  project_context: "<brief description of project type, stack, stage>"

  task_id: "<uuid>"
  task_text: "<natural language task description>"
  task_category: "<architecture|backend|ai|frontend|optimization|cross-cutting>"
  task_difficulty: "<easy|medium|hard>"
  task_domains: ["<domain1>", "<domain2>"]
  timestamp: "<ISO 8601>"

  # Retrieval
  retrieval_query:
    category: "<same as task_category>"
    domains: ["<same as task_domains>"]
    roles: ["<expected roles>"]
    keywords: ["<extracted>"]
  retrieved_memories:
    - memory_id: "<id>"
      type: "<task|failure|success|pattern|anti-pattern|effectiveness|hypothesis>"
      relevance_score: <0.0-1.0>
      final_score: <0.0-1.0>
      used: true | false
      rejection_reason: "<if rejected>"

  # Decision
  router_decision:
    lead_agent: "<role>"
    support_agents: ["<role>"]
    confidence: "<high|ambiguous>"
  orchestrator_decision:
    team_formed: true | false
    team_size: <int>
    lead_role: "<role>"
    support_roles: ["<role>"]

  # Implementation
  implementation:
    duration: "<approximate>"
    approach: "<brief description>"
    challenges: ["<challenge1>", "<challenge2>"]
    result: "<success|partial|failure>"

  # Outcome
  outcome:
    result: "<success|partial|failure>"
    quality_score: <0.0-1.0>
    issues: ["<issue1>", "<issue2>"]
    notes: "<human-readable notes>"

  # Feedback
  human_feedback:
    reviewer: "<person or role>"
    feedback_text: "<natural language feedback>"
    memory_helpful: true | false
    memory_harmful: true | false
    memory_neutral: true | false
    reason: "<why memory was helpful/harmful/neutral>"

  # Memory Evaluation
  memory_usefulness: "<helpful|neutral|harmful|unknown>"
  memory_influence: true | false
  decision_change: "<none|role_added|role_removed|role_reordered|strategy_changed|confidence_changed>"
  memory_outcome: "<helpful|neutral|harmful|unknown>"
  # Note: memory_influence ≠ memory_outcome
  # Memory can influence a decision but the outcome may still be harmful

  # Context
  context_compatibility:
    architecture_match: "<high|medium|low>"
    technology_match: "<high|medium|low>"
    scale_match: "<high|medium|low>"
    project_stage_match: "<high|medium|low>"
    overall: "<high|medium|low>"
    reason: "<explanation>"

  # Insights
  new_insight: "<optional — new observation from this task>"
  new_memory_candidate: true | false
  misapplication: true | false
  misapplication_detail: "<if misapplied>"

  # Evidence
  evidence_level: "real_project_validated"
  confidence: "<low|medium|high>"
  status: "<observed|repeated|validated>"
```

---

## 5. Memory Usefulness

Every memory retrieval must be evaluated for usefulness:

```yaml
memory_usefulness:
  helpful:   # Memory improved the decision or outcome
    criteria:
      - informed a better role selection
      - prevented a known failure pattern
      - confirmed a correct decision
      - raised awareness of a risk

  neutral:   # Memory was present but had no measurable impact
    criteria:
      - memory matched but decision was already correct
      - memory was too low-confidence to influence
      - memory was relevant but not actionable

  harmful:   # Memory led to a worse decision or outcome
    criteria:
      - memory suggested a wrong role
      - memory caused team inflation
      - memory was misapplied to wrong context
      - memory overrode correct engineering judgment

  unknown:   # Cannot yet determine if memory was helpful
    criteria:
      - outcome not yet measured
      - too early to tell
      - insufficient feedback
```

---

## 6. Memory Influence vs Memory Outcome

These are distinct concepts:

```yaml
# Example 1: Influence + Helpful Outcome
memory_influence: true
decision_change: "security_review_earlier"
outcome: "helpful"
reason: "Historical payment failure memory caused earlier security review, preventing repeated sequencing issue."

# Example 2: Influence + Harmful Outcome
memory_influence: true
decision_change: "add_database_engineer"
outcome: "harmful"
reason: "Memory suggested database-engineer for a simple CRUD task. Added unnecessary role overhead."

# Example 3: No Influence + Neutral
memory_influence: false
decision_change: "none"
outcome: "neutral"
reason: "Memory was retrieved but all scores were below threshold. No changes made."

# Example 4: Influence + Unknown
memory_influence: true
decision_change: "role_reordered"
outcome: "unknown"
reason: "Reordered roles based on effectiveness memory. Too early to evaluate impact."
```

---

## 7. Context Compatibility

Memory from one context may not apply to another. Before applying memory, evaluate:

```yaml
context_compatibility:
  architecture_match:
    high: "Same architecture pattern (e.g., both microservices)"
    medium: "Similar patterns with differences"
    low: "Different architecture (e.g., memory from microservices, current is monolith)"

  technology_match:
    high: "Same technology stack"
    medium: "Overlapping technologies"
    low: "Different technology stack"

  scale_match:
    high: "Similar scale (users, data volume, throughput)"
    medium: "Similar order of magnitude"
    low: "Different scale by orders of magnitude"

  project_stage_match:
    high: "Same project stage (e.g., both greenfield)"
    medium: "Adjacent stages"
    low: "Different stages (e.g., memory from mature project, current is prototype)"

  overall:
    high: "Memory is highly applicable"
    medium: "Memory may apply with caution"
    low: "Memory is likely not applicable — reduce confidence"
```

---

## 8. Memory Misapplication

When memory is correctly retrieved but incorrectly applied:

```yaml
misapplication:
  example:
    historical_context: "microservices → use distributed transaction"
    current_context: "modular monolith"
    error: "Applied Saga pattern to monolith"
    result: "Increased system complexity unnecessarily"
    lesson: "Always check context compatibility before applying memory"

  detection:
    - context_compatibility.overall == "low"
    - human_feedback indicates wrong application
    - implementation result contradicts expected outcome

  action:
    - record as misapplication failure
    - create failure memory for future reference
    - do NOT lower the original memory's score (it was valid in its context)
```

---

## 9. Human Feedback

Real engineering feedback must come from a human developer or reviewer, not from the agent itself:

```yaml
human_feedback:
  reviewer: "<name or role>"
  date: "<ISO 8601>"

  feedback_text: "<natural language>"

  memory_helpful: true | false
  memory_helpful_detail: "<which memory and why>"

  memory_harmful: true | false
  memory_harmful_detail: "<which memory and why>"

  suggestions: "<optional improvements>"

  overall_assessment: "<brief summary>"
```

---

## 10. Evidence Promotion Pipeline

Memory evidence levels are NOT automatically promoted:

```text
benchmark_evaluated (0.6)
  ↓
  Requires: 1 real project observation
  ↓
real_project_observed (0.7)
  ↓
  Requires: 2+ independent real project observations, no contradiction
  ↓
real_project_validated (0.8)
  ↓
  Requires: 3+ independent observations, consistent positive outcomes
  ↓
trusted (0.9)
  ↓
  Requires: 5+ observations, multiple project types, no harmful outcomes
  ↓
production_validated (1.0)
```

**Rule**: One observation is NOT enough for promotion. Never auto-promote.

---

## 11. Privacy and Redaction

Real projects may contain sensitive data. Always redact:

```yaml
redaction_rules:
  always_redact:
    - API_KEY
    - PASSWORD
    - TOKEN
    - SECRET
    - CREDENTIAL
    - PRIVATE_KEY
    - DB_PASSWORD
    - ACCESS_KEY

  context_redact:
    - customer_names
    - proprietary_algorithm_details
    - internal_URLs
    - private_repository_paths

  never_store:
    - source_code (store insights, not code)
    - database_dumps
    - configuration_files_with_secrets
    - user_data
    - PII (Personally Identifiable Information)

  redaction_format:
    replaced_with: "<REDACTED>"
    example: "API_KEY=<REDACTED>"
```

**Principle**: Memory stores engineering experience, not project secrets.

---

## 12. Feedback Metrics

```yaml
metrics:
  memory_usage_rate:
    formula: "tasks_with_memory_used / total_tasks"
    target: "track over time"

  memory_influence_rate:
    formula: "tasks_with_memory_influence / tasks_with_memory_used"
    target: "track, not maximize"

  memory_helpful_rate:
    formula: "helpful_outcomes / evaluated_outcomes"
    target: "> 50%"
    warning: "If < 30%, investigate"

  memory_neutral_rate:
    formula: "neutral_outcomes / evaluated_outcomes"
    target: "track"

  memory_harmful_rate:
    formula: "harmful_outcomes / evaluated_outcomes"
    target: "< 10%"
    critical: "If > 10%, trigger kill switch review"

  memory_induced_regression_rate:
    formula: "regressions / tasks_with_memory"
    target: "= 0"
    critical: "If > 0, immediate investigation"

  memory_reuse_rate:
    formula: "memories_used_multiple_times / total_memories"
    target: "track"

  new_insight_rate:
    formula: "tasks_generating_new_insight / total_tasks"
    target: "track"
```

---

## 13. Insufficient Evidence

If fewer than 10 real project tasks have been evaluated with Memory:

```yaml
status: PROVISIONAL
real_project_evidence: insufficient
action: "Continue collecting. Do not claim statistical significance."
```

Do not compute percentages with fewer than 10 samples. Record raw counts instead.

---

*Real Project Feedback Protocol v1.0. Ready for real project data collection.*