# Runtime Policy — Memory Mode Control

## 1. Purpose

This policy defines the operational modes for the Memory Decision Support system and the conditions under which mode transitions occur.

Memory is a **supporting layer**, not a critical dependency. The system must always be able to fall back to baseline operation.

---

## 2. Memory Modes

### 2.1 `enabled`

```yaml
mode: enabled
behavior: "Memory-augmented decision making"
description: "Memory Retrieval is active. Router and Orchestrator consume memory context alongside Router Rules."
pipeline:
  - Task Classification
  - Memory Retrieval
  - Router Rules + Memory → Decision
  - Orchestrator Patterns + Memory → Team Formation
```

### 2.2 `fallback`

```yaml
mode: fallback
behavior: "Memory is queried but results are logged-only, not applied to decisions"
description: "Memory Retrieval still runs but its output is recorded for analysis only. Decisions are made by Router Rules alone."
pipeline:
  - Task Classification
  - Memory Retrieval (log only)
  - Router Rules → Decision
  - Orchestrator Patterns → Team Formation
trigger:
  - "memory_harmful_rate > 10% in last 10 evaluations"
  - "memory_induced_regression detected"
  - "manual override by developer"
```

### 2.3 `disabled`

```yaml
mode: disabled
behavior: "Memory Retrieval is completely bypassed"
description: "No memory queries are made. System operates as baseline Router/Orchestrator."
pipeline:
  - Task Classification
  - Router Rules → Decision
  - Orchestrator Patterns → Team Formation
trigger:
  - "memory_harmful_rate > 20%"
  - "multiple regression events"
  - "memory system unavailable or corrupted"
  - "manual override by developer"
```

---

## 3. Mode Transition Rules

```text
enabled → fallback:
  Trigger: memory_harmful_rate > 10% (rolling 10 evaluations)
  Action: Memory queries continue but results are logged-only
  Recovery: 10 consecutive evaluations with harmful_rate = 0

fallback → disabled:
  Trigger: memory_harmful_rate > 20% OR 2+ regression events
  Action: All memory queries stop
  Recovery: Human review and explicit re-enable

fallback → enabled:
  Trigger: 10 consecutive evaluations with harmful_rate = 0 AND human approval
  Action: Resume memory-augmented decisions

disabled → enabled:
  Trigger: System fix verified + human review + explicit approval
  Action: Full re-enable
```

---

## 4. Current State

```yaml
current_mode: enabled
since: 2026-08-30
reason: "Phase 5.4 integration complete. No real project data yet — safe to enable."
last_evaluated: N/A
harmful_rate: N/A (no real project data)
regression_events: 0
```

---

## 5. Safety Thresholds

```yaml
thresholds:
  memory_harmful_rate_warning: 10%
  memory_harmful_rate_critical: 20%
  memory_induced_regression_warning: 1 event
  memory_induced_regression_critical: 2 events

  min_evaluations_for_metrics: 10  # Don't compute rates with < 10 samples
  rolling_window: 10               # Look at last 10 evaluations
```

---

## 6. Override

```yaml
manual_override:
  allowed: true
  by: "developer or system administrator"
  requires: "explicit confirmation"
  logged: "runtime/logs/memory-decision-history.md"

  commands:
    enable: "Set memory_mode to enabled"
    fallback: "Set memory_mode to fallback"
    disable: "Set memory_mode to disabled"
```

---

## 7. Monitoring

```yaml
monitoring:
  check_interval: "after every 10 real project evaluations"
  metrics_logged: "runtime/logs/real-project-memory-feedback.md"
  alert_condition: "memory_harmful_rate > 10% OR regression detected"
  alert_action: "review and consider fallback mode"
```

---

## 8. Principle

```text
Memory is a supporting layer.
System must function without it.
Memory failures must degrade gracefully.
Safety thresholds are non-negotiable.
```

---

*Runtime Policy v1.0. Current mode: enabled.*