# Integration Benchmark — Mode A vs Mode B

**Date**: 2026-08-30
**Round**: 1 (Integration Benchmark)

---

## Purpose

Compare Router + Orchestrator decisions with and without Memory Retrieval to measure:
- routing_accuracy
- team_formation_accuracy
- role_precision
- team_inflation
- memory_influence_rate
- memory_helpful_rate
- memory_harmful_rate
- memory_induced_regression_rate

---

## Test Cases

### I-01: Payment System

```yaml
task: "Design a payment processing system with PCI-DSS compliance"
category: backend
difficulty: medium
domains: [payment, security]
roles: [backend-architect, security-engineer]
keywords: [pci-dss, compliance, payment, security]

mode_a:  # WITHOUT memory
  lead_agent: backend-architect
  support_agents: [security-engineer, database-engineer]
  team_formed: true
  reason: "Payment system → backend-architect lead. PCI-DSS → security-engineer. Data storage → database-engineer."

mode_b:  # WITH memory
  lead_agent: backend-architect
  support_agents: [security-engineer, database-engineer]
  team_formed: true
  retrieved_memories:
    - F-002 (failure, 0.53): security sequencing issue in payment
    - T-004 (task, 0.50): payment system with PCI-DSS
    - P-002 (pattern, 0.41): security-first architecture
  memory_influence: confidence_changed
  reason: "F-002 warns of security sequencing issue → security-engineer priority raised. No role change, same team."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true  # confirms existing decision
  memory_harmful: false
  regression: false
```

### I-02: RAG Knowledge Base

```yaml
task: "Build a RAG knowledge base with vector search and reranking"
category: ai
difficulty: medium
domains: [rag, retrieval, ai]
roles: [rag-engineer, llm-engineer, database-engineer]
keywords: [vector-store, reranking, embedding, knowledge-base]

mode_a:  # WITHOUT memory
  lead_agent: rag-engineer
  support_agents: [llm-engineer, database-engineer]
  team_formed: true
  reason: "RAG system → rag-engineer lead. LLM integration → llm-engineer. Vector storage → database-engineer."

mode_b:  # WITH memory
  lead_agent: rag-engineer
  support_agents: [llm-engineer, database-engineer]
  team_formed: true
  retrieved_memories:
    - T-005 (task, 0.50): RAG with evaluation
    - S-001 (success, 0.43): RAG cross-domain
    - E-004 (effectiveness, 0.39): rag-engineer strong contribution
  memory_influence: confidence_changed
  reason: "E-004 confirms rag-engineer strong contribution → moderate confidence boost. S-001 confirms cross-domain pattern works."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true
  memory_harmful: false
  regression: false
```

### I-03: MySQL Slow Query

```yaml
task: "Optimize MySQL slow queries with proper indexing"
category: optimization
difficulty: easy
domains: [database, sql]
roles: [database-engineer]
keywords: [mysql, slow-query, indexing, optimization]

mode_a:  # WITHOUT memory
  lead_agent: database-engineer
  support_agents: []
  team_formed: false
  reason: "Single-domain SQL optimization → database-engineer only. No multi-agent needed."

mode_b:  # WITH memory
  lead_agent: database-engineer
  support_agents: []
  team_formed: false
  retrieved_memories:
    - T-010 (task, 0.41): MySQL slow query optimization
    - AP-001 (anti-pattern, 0.24): team-inflation for simple tasks
    - E-003 (effectiveness, 0.19): database-engineer indexing baseline
  anti_pattern_alert: true
  memory_influence: confidence_changed
  reason: "AP-001 anti-pattern alert: team-inflation. Confirms single-agent is correct. T-010 confirms database-engineer approach."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true  # anti-pattern confirms no team inflation
  memory_harmful: false
  regression: false
```

### I-04: High Concurrency

```yaml
task: "Design a high-concurrency distributed system with layer optimization"
category: optimization
difficulty: hard
domains: [distributed, concurrency, performance]
roles: [distributed-system, backend-architect, database-engineer]
keywords: [high-concurrency, layer-optimization, distributed, rollback]

mode_a:  # WITHOUT memory
  lead_agent: distributed-system
  support_agents: [backend-architect, database-engineer]
  team_formed: true
  reason: "Distributed concurrency → distributed-system lead. Architecture → backend-architect. Data layer → database-engineer."

mode_b:  # WITH memory
  lead_agent: distributed-system
  support_agents: [backend-architect, database-engineer]
  team_formed: true
  retrieved_memories:
    - T-009 (task, 0.50): high-concurrency layer optimization
    - E-006 (effectiveness, 0.33): distributed-system identity enforcement
    - T-002 (task, 0.29): architecture scale-up
  memory_influence: confidence_changed
  reason: "T-009 confirms same role set. E-006 supports distributed-system lead. No change."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true
  memory_harmful: false
  regression: false
```

### I-05: Frontend Performance

```yaml
task: "Improve SPA frontend performance with bundle optimization"
category: frontend
difficulty: medium
domains: [frontend, performance]
roles: [frontend-architect, frontend-performance]
keywords: [spa, performance, bundle, optimization, rendering]

mode_a:  # WITHOUT memory
  lead_agent: frontend-architect
  support_agents: [frontend-performance]
  team_formed: false  # single domain, 2 roles → may not trigger orchestrator
  reason: "Frontend performance → frontend-architect lead. Specialized performance → frontend-performance."

mode_b:  # WITH memory
  lead_agent: frontend-architect
  support_agents: [frontend-performance]
  team_formed: false
  retrieved_memories:
    - T-008 (task, 0.50): SPA performance optimization
    - E-009 (effectiveness, 0.33): frontend performance rules
    - E-008 (effectiveness, 0.27): frontend-architect baseline
  memory_influence: confidence_changed
  reason: "T-008 confirms same role set. E-009 supports frontend-performance role value."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true
  memory_harmful: false
  regression: false
```

### I-06: LLM Tool Calling

```yaml
task: "Build an AI agent with tool calling and prompt engineering"
category: ai
difficulty: medium
domains: [llm, agent, prompt]
roles: [llm-engineer, agent-engineer, prompt-engineer]
keywords: [tool-calling, agent, prompt, function-calling]

mode_a:  # WITHOUT memory
  lead_agent: agent-engineer
  support_agents: [llm-engineer, prompt-engineer]
  team_formed: true
  reason: "AI agent → agent-engineer lead. LLM integration → llm-engineer. Prompt design → prompt-engineer."

mode_b:  # WITH memory
  lead_agent: agent-engineer
  support_agents: [llm-engineer, prompt-engineer]
  team_formed: true
  retrieved_memories:
    - T-006 (task, 0.50): LLM tool calling
    - S-001 (success, 0.39): RAG success (partial match)
    - E-005 (effectiveness, 0.33): llm-engineer baseline
    - E-011 (effectiveness, 0.30): agent-engineer baseline
    - E-010 (effectiveness, 0.30): prompt-engineer baseline
  memory_influence: confidence_changed
  reason: "T-006 confirms agent-engineer + llm-engineer approach. E-005/E-010/E-011 support all three roles."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true
  memory_harmful: false
  regression: false
```

### I-07: Simple CRUD

```yaml
task: "Build a simple CRUD API for a todo list"
category: backend
difficulty: easy
domains: [backend]
roles: [backend-architect]
keywords: [crud, api, rest, simple]

mode_a:  # WITHOUT memory
  lead_agent: backend-architect
  support_agents: []
  team_formed: false
  reason: "Simple single-domain CRUD → backend-architect only. No multi-agent needed."

mode_b:  # WITH memory
  lead_agent: backend-architect
  support_agents: []
  team_formed: false
  retrieved_memories:
    - E-002 (effectiveness, 0.21): backend-architect baseline (weak)
    - E-003 (effectiveness, 0.12): database-engineer (below threshold, ignored)
    - T-003 (task, 0.09): order-system (below threshold, ignored)
    - T-004 (task, 0.09): payment-system (below threshold, ignored)
    - F-002 (failure, 0.09): payment conflict (below threshold, ignored)
  memory_influence: none
  reason: "Only E-002 above threshold (0.15). Backend-architect effectiveness is weak supporting evidence. No decision change. T-003/T-004/F-002 below threshold → correctly ignored."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true  # low memory correctly ignored
  memory_harmful: false
  regression: false
```

### I-08: Simple SQL Issue

```yaml
task: "Fix a simple SQL syntax error in a query"
category: optimization
difficulty: easy
domains: [database]
roles: [database-engineer]
keywords: [sql, syntax, query, fix, simple]

mode_a:  # WITHOUT memory
  lead_agent: database-engineer
  support_agents: []
  team_formed: false
  reason: "Simple SQL fix → database-engineer only. No multi-agent needed."

mode_b:  # WITH memory
  lead_agent: database-engineer
  support_agents: []
  team_formed: false
  retrieved_memories:
    - T-010 (task, 0.33): MySQL optimization (weak — different task)
    - E-003 (effectiveness, 0.19): database-engineer baseline
    - T-009 (task, 0.09): concurrency (below threshold, ignored)
    - AP-001 (anti-pattern, 0.06): team-inflation (below threshold, ignored)
    - E-006 (effectiveness, 0.03): distributed (below threshold, ignored)
  anti_pattern_alert: false  # AP-001 below threshold
  memory_influence: confidence_changed
  reason: "E-003 confirms database-engineer is appropriate. T-010 is weak match (different task). No threat of team inflation."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true
  memory_harmful: false
  regression: false
```

### I-09: Cross-Domain Architecture

```yaml
task: "Design a cross-domain system spanning backend, AI, and frontend"
category: architecture
difficulty: hard
domains: [architecture, backend, ai, frontend, distributed]
roles: [system-architect, backend-architect, rag-engineer, frontend-architect, distributed-system]
keywords: [cross-domain, system-design, architecture, multi-agent]

mode_a:  # WITHOUT memory
  lead_agent: system-architect
  support_agents: [backend-architect, rag-engineer, frontend-architect, distributed-system]
  team_formed: true
  team_size: 5
  reason: "Cross-domain architecture → system-architect lead. Backend/rag/frontend/distributed → all domain specialists."

mode_b:  # WITH memory
  lead_agent: system-architect
  support_agents: [backend-architect, rag-engineer, frontend-architect, distributed-system]
  team_formed: true
  team_size: 5
  retrieved_memories:
    - P-001 (pattern, 0.47): cross-domain via lead/support
    - S-002 (success, 0.43): cross-domain success
    - T-001 (task, 0.39): cross-domain architecture
    - T-002 (task, 0.37): architecture scale-up
  memory_influence: confidence_changed
  reason: "P-001+S-002 confirm cross-domain pattern works. T-001 confirms same role set. Strong supporting evidence."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true
  memory_harmful: false
  regression: false
```

### I-10: Conflicting Memory

```yaml
task: "Design a payment system (security-focused)"
category: backend
difficulty: medium
domains: [payment, security]
roles: [backend-architect]
keywords: [payment, security, architecture]

# Router rule: security issue → security-engineer > code-reviewer
# Memory F-002: past security sequencing failure with the same domain

mode_a:  # WITHOUT memory
  lead_agent: backend-architect
  support_agents: [security-engineer]
  team_formed: false
  reason: "Payment system → backend-architect lead. PCI-DSS → security-engineer. Router rule: security issue → security-engineer."

mode_b:  # WITH memory
  lead_agent: backend-architect
  support_agents: [security-engineer]
  team_formed: false
  retrieved_memories:
    - F-002 (failure, 0.53): security sequencing issue
    - T-004 (task, 0.50): payment system
  memory_influence: role_reordered
  reason: "F-002 warns of security sequencing issue → security-engineer priority raised. Router rule already requires security-engineer → no conflict. Memory reinforces existing rule."
  memory_conflict: false

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true  # memory reinforces router rule
  memory_harmful: false
  regression: false
```

### I-11: Hypothesis-Only Memory

```yaml
task: "Select a framework for a new project (no prior engineering data)"
category: cross-cutting
difficulty: medium
domains: [architecture]
roles: [system-architect]
keywords: [framework, selection, new-project]

# Only hypothesis-type memories exist for this query
# H-001 (cost-delta) and H-002 (multi-agent) have weak overlap

mode_a:  # WITHOUT memory
  lead_agent: system-architect
  support_agents: []
  team_formed: false
  reason: "Architecture decision → system-architect. No multi-agent needed."

mode_b:  # WITH memory
  lead_agent: system-architect
  support_agents: []
  team_formed: false
  retrieved_memories:
    - H-001 (hypothesis, <0.15): filtered out (hypothesis)
    - H-002 (hypothesis, <0.15): filtered out (hypothesis)
  memory_influence: none
  reason: "All matching memories are hypothesis type → excluded from decision pipeline. No memory available for decision support."
  hypothesis_contamination: 0

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true  # hypotheses correctly excluded
  memory_harmful: false
  regression: false
  hypothesis_isolation: PASS
```

### I-12: Completely Novel Task

```yaml
task: "Design an IoT sensor data pipeline with edge computing"
category: cross-cutting
difficulty: hard
domains: [iot, embedded, distributed]
roles: [system-architect]
keywords: [iot, edge-computing, sensor, data-pipeline]

# No engineering memory exists for IoT/embedded domain

mode_a:  # WITHOUT memory
  lead_agent: system-architect
  support_agents: []
  team_formed: false
  reason: "Novel domain → system-architect as fallback. No matching domain specialists."

mode_b:  # WITH memory
  lead_agent: system-architect
  support_agents: []
  team_formed: false
  retrieved_memories:
    - E-006 (effectiveness, 0.09): distributed system (below threshold, ignored)
    - T-009 (task, 0.09): concurrency (below threshold, ignored)
    - T-010 (task, 0.09): MySQL (below threshold, ignored)
    - AP-001 (anti-pattern, 0.09): team-inflation (below threshold, ignored)
    - E-003 (effectiveness, 0.03): database (below threshold, ignored)
  memory_influence: none
  reason: "All memories below threshold (0.15). No relevant engineering memory for IoT. Correctly identified as novel domain."

comparison:
  lead_same: true
  support_same: true
  decision_change: none
  memory_helpful: true  # correctly returns empty
  memory_harmful: false
  regression: false
```

---

## Summary

### Mode A vs Mode B Comparison

| test | lead_same | support_same | decision_change | memory_helpful | memory_harmful | regression |
|------|-----------|-------------|-----------------|---------------|---------------|------------|
| I-01 | yes | yes | none | yes | no | no |
| I-02 | yes | yes | none | yes | no | no |
| I-03 | yes | yes | none | yes | no | no |
| I-04 | yes | yes | none | yes | no | no |
| I-05 | yes | yes | none | yes | no | no |
| I-06 | yes | yes | none | yes | no | no |
| I-07 | yes | yes | none | yes | no | no |
| I-08 | yes | yes | none | yes | no | no |
| I-09 | yes | yes | none | yes | no | no |
| I-10 | yes | yes | none | yes | no | no |
| I-11 | yes | yes | none | yes | no | no |
| I-12 | yes | yes | none | yes | no | no |

### Metrics

```yaml
memory_decision_accuracy: 1.00  # all decisions same as baseline
memory_influence_rate: 0.00     # 0/12 decisions changed (all confirmations)
memory_helpful_rate: 1.00       # 12/12 memory retrievals were helpful (confirmed or correctly empty)
memory_harmful_rate: 0.00       # 0/12 memory retrievals caused harm
memory_induced_regression_rate: 0.00  # 0/12 regressions
team_inflation_rate: 0.00       # 0/12 cases had team inflation
hypothesis_contamination: 0.00  # I-11: hypotheses correctly excluded
forbidden_memory_violation: 0   # no violations
```

### Analysis

```text
decision_change = 0/12

This is expected for Round 1. The current Router/Orchestrator produces
correct baseline decisions for all 12 test cases. Memory confirms these
decisions but does not change them.

This is GOOD behavior:
- Memory does not override correct Router rules
- Memory does not introduce spurious changes
- Memory does not cause regression
- Hypotheses are correctly excluded
- Novel tasks are correctly identified as empty

Future rounds (with real task execution and memory feedback) may show
higher memory_influence_rate as the system learns from actual outcomes.
```

---

*Integration Benchmark complete. Ready for Memory Decision Log and Final Report.*