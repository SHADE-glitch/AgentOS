# Memory Decision History

**Purpose**: Runtime log of memory-influenced Router and Orchestrator decisions.

**Protocol**: `memory/decision-support-protocol.md`

---

## Record Template

```yaml
timestamp: "<ISO 8601>"
task_id: "<uuid>"
task_text: "<natural language task description>"
task_category: "<architecture|backend|ai|frontend|optimization|cross-cutting>"
task_difficulty: "<easy|medium|hard>"

retrieved_memories:
  - memory_id: "<id>"
    type: "<type>"
    final_score: <0.0-1.0>
    used: true | false
    rejection_reason: "<if rejected>"

router_decision:
  lead_agent: "<role>"
  support_agents: ["<role>"]
  confidence: "<high|ambiguous>"
  fallback_used: true | false

orchestrator_decision:
  team_formed: true | false
  team_size: <int>
  lead_role: "<role>"
  support_roles: ["<role>"]
  pattern_used: "<pattern_name or null>"
  anti_pattern_alert: true | false

memory_influence:
  used: true | false
  memory_count: <int>
  influenced_router: true | false
  influenced_orchestrator: true | false
  decision_change: "<none|role_added|role_removed|role_reordered|strategy_changed|confidence_changed>"
  reason: "<explanation>"
  memory_conflict: true | false
  conflict_resolution: "<if conflict>"

decision_provenance:
  memories_considered: <int>
  memories_used: <int>
  memories_rejected: <int>
  memories_below_threshold: <int>
  router_rules_used: ["<rule>"]
  final_decision: "<summary>"
  decision_reason: "<justification>"

human_review:
  required: true | false
  approved: true | false
  reviewer: "<user>"

outcome:
  measured: true | false
  result: "<success|partial|failure>"
  notes: "<optional>"
```

---

## Records

### Round 1 — Integration Benchmark (2026-08-30)

*No real task execution yet. 12 benchmark test cases in `tests/memory/integration/integration-benchmark.md`.*

*Records will be appended here as real tasks are routed with memory retrieval.*

---

*Decision History Log initialized. Ready for production use.*