# Decision-Support Protocol

## 1. Purpose

This protocol defines how Engineering Memory influences Router and Orchestrator decisions without owning them.

```text
Current Task + Router Rules + Relevant Memory = Decision
```

Memory is a **supporting input**, never the sole decision authority.

---

## 2. Decision Context Schema

Every decision that involves memory must emit this context:

```yaml
decision_context:
  task_id: "<uuid>"
  task_text: "<natural language task description>"
  task_category: "<architecture|backend|ai|frontend|optimization|cross-cutting>"
  task_difficulty: "<easy|medium|hard>"
  task_domains: ["<domain1>", "<domain2>"]
  task_roles: ["<role1>", "<role2>"]

  retrieval_query:
    category: "<same as task_category>"
    difficulty: "<same as task_difficulty>"
    domains: ["<same as task_domains>"]
    roles: ["<same as task_roles>"]
    keywords: ["<extracted from task_text>"]

  retrieved_memories:
    - memory_id: "<id>"
      type: "<task|failure|success|pattern|anti-pattern|effectiveness|hypothesis>"
      relevance_score: <0.0-1.0>
      evidence_weight: <0.0-1.0>
      final_score: <relevance * evidence_weight>
      confidence: "<low|medium|high>"
      applicability: "<reason this memory is relevant to this task>"
      warning: "<optional — required for hypothesis type>"

  router_decision:
    lead_agent: "<role>"
    support_agents: ["<role1>", "<role2>"]
    confidence: "<high|ambiguous>"
    fallback_used: true | false

  orchestrator_decision:
    team_formed: true | false
    team_size: <int>
    lead_role: "<role>"
    support_roles: ["<role1>", "<role2>"]
    pattern_used: "<pattern_name or null>"
    dependency_order: ["<layer0>", "<layer1>"]

  memory_influence:
    used: true | false
    memory_count: <int>
    influenced_router: true | false
    influenced_orchestrator: true | false
    decision_change: "<none|role_added|role_removed|role_reordered|strategy_changed|confidence_changed>"
    reason: "<natural language explanation of influence>"
    memory_conflict: true | false
    conflict_resolution: "<router_rule_priority|evidence_insufficient|user_override>"

  decision_provenance:
    memories_considered: <int>
    memories_used: <int>
    memories_rejected: <int>
    memories_below_threshold: <int>
    router_rules_used: ["<rule1>", "<rule2>"]
    final_decision: "<summary>"
    decision_reason: "<natural language justification>"
```

---

## 3. Memory Influence Tracking

### 3.1 Influence Types

```yaml
decision_change:
  none:                # Memory present but did not change decision
  role_added:          # Memory caused a role to be added to the team
  role_removed:        # Memory caused a role to be removed from the team
  role_reordered:      # Memory caused a role's priority to change
  strategy_changed:    # Memory caused a different execution strategy
  confidence_changed:  # Memory raised or lowered decision confidence
```

### 3.2 Influence Must Be Explainable

Every `memory_influence` entry must include a `reason` field that answers:

> Why did this memory change (or not change) the decision?

### 3.3 Memory Conflict Resolution

When memory suggests a different decision than Router rules:

```yaml
memory_conflict: true
resolution: router_rule_priority
reason: "Router rule: security issue → security-engineer > code-reviewer. Memory suggestion (code-reviewer lead) was overridden."
```

Record conflicts for future Evolution Engine analysis.

---

## 4. Memory Type Decision Rules

### 4.1 Task Memory

```yaml
task_memory:
  usage: "Inform role selection with similar past tasks"
  influence: role_added | role_removed | confidence_changed
  condition: "final_score >= 0.15 and type == task"
  priority: "below Router Rules"
  example: "Past payment system task used backend-architect + security-engineer → suggest same roles"
```

### 4.2 Failure Memory

```yaml
failure_memory:
  usage: "Warn about known conflicts and adjust role priority"
  influence: role_reordered | confidence_changed | strategy_changed
  condition: "final_score >= 0.15 and type == failure"
  priority: "below Router Rules, above low-confidence Memory"
  example: "Past payment system had security sequencing issue → raise security-engineer priority"
  note: "Failure memory NEVER removes roles — it only reorders or adds"
```

### 4.3 Success Memory

```yaml
success_memory:
  usage: "Support evidence for role selection patterns"
  influence: confidence_changed
  condition: "final_score >= 0.15 and type == success"
  priority: "supporting evidence only"
  example: "Cross-domain pattern worked well → moderate confidence boost"
```

### 4.4 Pattern Memory

```yaml
pattern_memory:
  usage: "Team formation patterns (already consumed by Orchestrator)"
  influence: strategy_changed
  condition: "final_score >= 0.15 and type == pattern"
  priority: "combined with memory/patterns/ matching"
  example: "Cross-domain architecture pattern → system-architect lead + domain specialists"
```

### 4.5 Anti-Pattern Memory

```yaml
anti_pattern_memory:
  usage: "Prevent team inflation and role waste"
  influence: role_removed | strategy_changed
  condition: "final_score >= 0.15 and type == anti-pattern"
  priority: "high alert — raises activation bar for multi-agent"
  example: "Simple SQL task + team-inflation anti-pattern → prefer single-agent"
  note: "Anti-pattern raises alert but does not block team formation"
```

### 4.6 Effectiveness Memory

```yaml
effectiveness_memory:
  usage: "Per-role quality baselines and contribution evidence"
  influence: role_reordered | confidence_changed
  condition: "final_score >= 0.15 and type == effectiveness"
  priority: "supporting evidence only"
  example: "rag-engineer showed strong contribution in RAG tasks → moderate confidence boost"
```

### 4.7 Hypothesis Memory

```yaml
hypothesis_memory:
  usage: "NEVER used for decision. Informational only."
  influence: none
  condition: "always flagged with warning, never applied"
  priority: "excluded from decision pipeline"
  warning: "This memory is an unvalidated hypothesis. Do not use for routing or team formation."
```

---

## 5. Decision Priority Hierarchy

```text
Priority 1: Current Task Requirements
  - Hard constraints from the user's explicit request
  - Cannot be overridden by any memory

Priority 2: Explicit Router Rules
  - skill-routing-matrix.md rules
  - Security, domain-specific, and fallback rules
  - Memory cannot override these

Priority 3: Safety / Hard Constraints
  - Role registry (skills/meta/role-registry.md)
  - Team size cap (7)
  - Dependency rules (C1-C6)
  - Memory cannot override these

Priority 4: High-Confidence Relevant Memory
  - final_score >= 0.30
  - evidence_level >= benchmark_evaluated
  - type != hypothesis
  - Can influence role selection, ordering, and confidence

Priority 5: Low-Confidence Memory
  - 0.15 <= final_score < 0.30
  - May be used as supporting evidence
  - Must not change the primary decision
  - Must be recorded with low confidence flag

Priority 6: Below-Threshold Memory
  - final_score < 0.15
  - Ignored — not used for any decision
  - Still recorded in provenance for audit
```

---

## 6. Decision Provenance

Every decision must be traceable:

```yaml
decision_provenance:
  task_id: "<uuid>"
  timestamp: "<ISO 8601>"

  memories_considered: <total in retrieval result>
  memories_used: <count applied to decision>
  memories_rejected: <count excluded by rules>
  memories_below_threshold: <count with final_score < 0.15>

  rejection_reasons:
    - memory_id: "<id>"
      reason: "<below_threshold|hypothesis|type_mismatch|confidence_insufficient|rule_conflict>"

  router_rules_applied: ["<rule1>", "<rule2>"]
  orchestrator_rules_applied: ["<R1>", "<C1>"]

  final_decision: "<summary of routing and team formation>"
  decision_reason: "<natural language justification>"

  human_review:
    required: true | false
    approved: true | false
    reviewer: "<user>"
```

---

## 7. Thresholds

```yaml
thresholds:
  min_final_score: 0.15        # Below this → ignore memory
  high_confidence: 0.30        # Above this → memory can influence decision
  hypothesis_contamination: 0  # Must always be 0
  forbidden_memory_violation: 0 # Must always be 0

  evidence_level_floor: benchmark_evaluated  # Minimum evidence for decision influence
```

---

## 8. Fallback Contract

```yaml
fallback:
  memory_available:
    behavior: "Memory-augmented decision"
    output: "decision_context with memory_influence"

  memory_unavailable:
    behavior: "Baseline decision (Router/Orchestrator without memory)"
    log: "memory_unavailable_fallback"
    output: "decision_context with memory_influence.used = false"

  memory_retrieval_error:
    behavior: "Baseline decision"
    log: "memory_retrieval_error: <error_message>"
    output: "decision_context with memory_influence.used = false"

  memory_retrieval_timeout:
    behavior: "Baseline decision after 5s timeout"
    log: "memory_retrieval_timeout"
    output: "decision_context with memory_influence.used = false"
```

---

## 9. Integration Contract

### 9.1 Router Integration

```text
Router Decision Pipeline (with Memory):

Step 1: Intent Detection
Step 2: Domain Classification
  ↓
Step 2a: Memory Retrieval
  - Query: classified task (category, domains, roles, keywords)
  - Retrieve: top-5 memories with scores
  - Filter: remove hypothesis, remove below-threshold
  ↓
Step 3: Lead Skill Selection
  - Input: Router Rules + High-Confidence Task Memory
  - Rule: Memory can suggest but Router Rules override
  ↓
Step 4: Supporting Skill Selection
  - Input: Router Rules + Effectiveness Memory + Failure Memory
  - Rule: Memory can suggest but Router Rules override
  ↓
Step 5: Confidence Evaluation
  - Input: Router Rules + Failure Memory (lowers confidence) + Success Memory (raises confidence)
  ↓
Step 6: Fallback
Step 7: Runtime Logging + Decision Provenance
```

### 9.2 Orchestrator Integration

```text
Orchestrator Decision Pipeline (with Memory):

Phase 1: Understand the task
Phase 2: Assess multi-agent need
  ↓
Phase 2a: Memory Retrieval
  - Query: classified task (category, domains, roles, keywords)
  - Retrieve: top-5 memories with scores
  - Filter: remove hypothesis, remove below-threshold
  ↓
Phase 2b: Anti-Pattern Check
  - If anti-pattern memory matches → raise activation bar
  - Simple single-domain tasks → prefer single-agent
  ↓
Phase 3: Build Team Plan
  - Pattern Matching: memory/patterns/ + pattern memory from retrieval
  - Role Selection: R1-R10 + failure memory (role ordering) + effectiveness memory (baselines)
  - Dependency Ordering: existing logic + failure memory (constraint awareness)
  ↓
Phase 4-7: (unchanged)
```

---

## 10. Prohibited Actions

Memory must NEVER:

```yaml
prohibited:
  - override Router Rules (Priority 2)
  - override Safety Constraints (Priority 3)
  - add a role not in role-registry.md
  - remove a role required by R1-R10
  - force team formation when activation conditions not met
  - block team formation when activation conditions are met
  - use hypothesis memory for any decision
  - automatically generate new memory from execution
  - automatically modify Skills or Router configuration
  - skip the human review gate
```

---

## 11. Observability Commitments

Every memory-influenced decision must produce:

```yaml
observability:
  - decision_context: full schema as defined in section 2
  - memory_influence: change type + reason
  - decision_provenance: traceable decision path
  - memory_decision_log: persisted to runtime/logs/memory-decision-history.md
  - human_review_gate: checkpoint status
```

---

*Decision-Support Protocol v1.0. Ready for Router and Orchestrator integration.*