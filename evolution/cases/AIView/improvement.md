# Improvement Plan — Agent OS Evolution

## Executive Summary

Based on the AIView project execution, the Agent OS shows strong analysis capabilities but weak execution reliability and cross-stack adaptation. This improvement plan addresses 6 critical patterns and proposes 12 specific changes to skills, workflow, and runtime rules.

---

## Part 1: Skill Updates

### SU-001: Enhance system-architect for Java Projects

**Current State**: Generic architecture analysis
**Problem**: Produces Python-centric solutions for Java projects
**Proposed Change**:

Add to `skills/architecture/system-architect/SKILL.md`:

```markdown
## 13. Technology Stack Awareness

Before generating any code or architecture:

1. Detect project tech stack from:
   - pom.xml (Maven/Gradle)
   - package.json (Node.js)
   - requirements.txt (Python)
   - go.mod (Go)

2. Load relevant knowledge base:
   - Java: ~/.agents/knowledge/java/
   - Python: ~/.agents/knowledge/python/
   - Frontend: ~/.agents/knowledge/frontend/

3. Explicitly state detected stack in output:
   "Detected: Java 21 + Spring Boot 3.3.5 + MyBatis-Plus"
```

**Validation**: Test with AIView project, verify Java-specific output

---

### SU-002: Add Interface-First Enforcement to backend-architect

**Current State**: Creates concrete @Service classes directly
**Problem**: Skips interface abstraction layer
**Proposed Change**:

Add to `skills/backend/backend-architect/SKILL.md`:

```markdown
## 12. Interface-First Rule

When refactoring or creating new services:

1. ALWAYS create interface first:
   - Create `src/main/java/.../IXxxService.java`
   - Verify file exists: `ls -la IXxxService.java`

2. THEN create implementation:
   - Create `XxxServiceImpl.java implements IXxxService`
   - Use @Service annotation

3. Add conditional injection when multiple implementations:
   @ConditionalOnProperty(name = "app.mode", havingValue = "ai")
   @Service
   public class AiXxxService implements IXxxService { }

4. Verify with:
   grep -r "implements IXxxService" --include="*.java"
```

**Validation**: Verify interface files exist before implementations

---

### SU-003: Add Critical Bug Detection to code-reviewer

**Current State**: General code review
**Problem**: Misses Spring-specific patterns like competing consumers
**Proposed Change**:

Add to `skills/engineering/code-reviewer/SKILL.md`:

```markdown
## 14. Spring Critical Pattern Checks

### Check 1: Competing RabbitMQ Consumers
```bash
# Find all @RabbitListener annotations
grep -r "@RabbitListener" --include="*.java"

# Check if any share queue name without @ConditionalOnProperty
# If queue name is same and no conditional injection → CRITICAL BUG
```

### Check 2: Missing Conditional Injection
```bash
# Find beans with AI dependencies
grep -r "ChatClient\|EmbeddingClient" --include="*.java"

# Verify each has @ConditionalOnProperty
# If missing → HIGH RISK
```

### Check 3: Dependency Direction
```bash
# Verify Controller → Service → Repository flow
# If Repository injected in Controller → VIOLATION
```
```

**Validation**: Run on AIView, verify detection of P0-1 bug

---

### SU-004: Add Test Enforcement to all Engineering Skills

**Current State**: Tests optional
**Problem**: No test coverage for new code
**Proposed Change**:

Add to all `skills/engineering/*/SKILL.md`:

```markdown
## 15. Test Requirement

For every new @Service class:
1. Create corresponding *Test.java
2. Add at least 1 test method
3. Run `mvn test` before completing task
4. Include test output in final report

Failure to include tests = Task Incomplete
```

**Validation**: Verify test files created with new services

---

## Part 2: Workflow Changes

### WF-001: Add Tech Stack Detection Step

**Current Flow**:
```
Task Received → Routing → Memory → Orchestration → Agent Execution
```

**Proposed Flow**:
```
Task Received → Tech Stack Detection → Routing → Memory → Orchestration → Agent Execution
```

**Implementation**:
Add to `skills/meta/agent-router/SKILL.md`:

```markdown
## Pre-Routing Step: Tech Stack Detection

Before routing, detect:
1. Project language (Java/Python/Go/etc.)
2. Framework (Spring/Django/Gin/etc.)
3. Build tool (Maven/Gradle/pip/etc.)

Store in routing context:
```yaml
detected_stack:
  language: java
  framework: spring-boot
  build_tool: maven
  version: 21
```

Pass to lead skill for adaptation.
```

---

### WF-002: Add Plan Validation Checkpoint

**Current Flow**:
```
Planning Phase → Implementation Phase
```

**Proposed Flow**:
```
Planning Phase → Plan Validation → Implementation Phase
```

**Implementation**:
Add validation step in `skills/meta/agent-orchestrator/SKILL.md`:

```markdown
## Plan Validation Gate

Before implementation begins:

1. Extract planned interfaces from plan document:
   grep -A5 "interface" REFACTORING_PLAN.md

2. Verify each interface will be created:
   - Check file paths exist in plan
   - Check implementation classes exist in plan

3. Add to execution checklist:
   - [ ] Interface IXxxService created
   - [ ] Implementation XxxServiceImpl created
   - [ ] Conditional injection added

4. Block implementation if validation fails
```

---

### WF-003: Add Incremental Verification Loop

**Current Flow**:
```
Implementation → Final Test
```

**Proposed Flow**:
```
Implementation → Micro Test → Next Implementation → ... → Final Test
```

**Implementation**:
Add to `skills/meta/collaboration-runtime/SKILL.md`:

```markdown
## Micro-Test Requirement

After each significant code change:
1. Run `mvn compile` (verify syntax)
2. Run `mvn test` (verify logic)
3. Capture output
4. If failure → STOP, fix before continuing

Never batch multiple changes before testing.
```

---

## Part 3: Runtime Rules

### RR-001: Add Execution Reliability Threshold

**Current State**: No reliability check
**Problem**: 50% execution success rate is unacceptable
**Proposed Change**:

Add to `runtime/runtime-contract.yaml`:

```yaml
reliability_threshold:
  min_success_rate: 0.8  # 80%
  max_consecutive_failures: 2
  fallback_action: switch_model_or_pause

enforcement:
  - if success_rate < 0.8:
      action: alert_user
      message: "Execution reliability below threshold. Consider model switch."
  - if consecutive_failures >= 2:
      action: pause_execution
      message: "Too many failures. Please review and confirm continuation."
```

---

### RR-002: Add Cross-Stack Protection

**Current State**: No stack validation
**Problem**: Python output in Java project
**Proposed Change**:

Add to `runtime/runtime-contract.yaml`:

```yaml
stack_protection:
  enabled: true
  rules:
    - if project_contains("pom.xml"):
        forbidden_output: ["import langchain", "import torch", "from transformers"]
        required_output: ["import org.springframework", "import java."]
    - if project_contains("package.json"):
        forbidden_output: ["import requests", "import flask"]
        required_output: ["import React", "import Vue"]

enforcement:
  - on_violation: reject_output
    message: "Output contains wrong tech stack. Regenerating..."
```

---

### RR-003: Add Quality Gate for Code Generation

**Current State**: No quality gate
**Problem**: Code generated without tests, with bugs
**Proposed Change**:

Add to `runtime/runtime-contract.yaml`:

```yaml
code_quality_gate:
  required_before_completion:
    - mvn_compile: pass
    - mvn_test: pass
    - no_competing_consumers: true
    - interface_exists: true
    - test_file_exists: true

  blocking_conditions:
    - if !mvn_compile:
        action: block
        message: "Code does not compile. Fix before continuing."
    - if competing_consumers:
        action: block
        message: "Critical bug detected: competing consumers. Fix immediately."
```

---

## Part 4: Memory Updates

### MU-001: Add Java Refactoring Patterns to Knowledge Base

**Location**: `~/.agents/knowledge/java/refactoring/`

**Files to Create**:

1. `spring-bean-isolation.md` — Patterns for conditional injection
2. `rabbitmq-consumer-patterns.md` — Competing consumer prevention
3. `interface-first-refactoring.md` — Interface abstraction rules
4. `mybatis-plus-patterns.md` — Entity/mapper best practices

---

### MU-002: Add Failure Patterns to Memory

**Location**: `~/.agents/memory/anti-patterns/`

**Files to Create**:

1. `competing-consumers.md` — FP-001 pattern
2. `plan-code-gap.md` — FP-002 pattern
3. `cross-stack-contamination.md` — FP-003 pattern

---

## Part 5: Evaluation Rule Updates

### ER-001: Add Reliability Metric

**Current Metrics**: Accuracy, Precision, Recall
**Proposed Addition**:

Add to `skills/meta/quality-evaluator/SKILL.md`:

```markdown
## 11. Reliability Metrics

### Execution Success Rate
- Formula: successful_executions / total_executions
- Threshold: >= 80%
- Action if below: Alert, suggest model switch

### Plan Adherence Rate
- Formula: implemented_interfaces / planned_interfaces
- Threshold: >= 90%
- Action if below: Require plan review

### Critical Bug Detection Rate
- Formula: bugs_caught_in_review / bugs_in_production
- Threshold: 100%
- Action if below: Enhance review checklists
```

---

## Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | RR-001 (Reliability Threshold) | 1h | High |
| P0 | RR-002 (Cross-Stack Protection) | 2h | High |
| P0 | SU-003 (Bug Detection) | 1h | High |
| P1 | SU-001 (Java Awareness) | 2h | Medium |
| P1 | SU-002 (Interface-First) | 1h | Medium |
| P1 | WF-001 (Tech Stack Detection) | 2h | Medium |
| P2 | SU-004 (Test Enforcement) | 1h | Medium |
| P2 | WF-002 (Plan Validation) | 2h | Medium |
| P2 | WF-003 (Incremental Verification) | 1h | Low |
| P3 | MU-001 (Java Knowledge) | 4h | Low |
| P3 | MU-002 (Failure Patterns) | 2h | Low |
| P3 | ER-001 (Reliability Metric) | 1h | Low |

**Total Estimated Effort**: 20 hours

---

## Expected Outcomes

After implementing these improvements:

1. **Execution Success Rate**: 50% → 85%
2. **Plan Adherence**: 55% → 85%
3. **Critical Bug Detection**: 60% → 95%
4. **Cross-Stack Contamination**: 30% → 5%
5. **Code Quality Score**: 6.5/10 → 8.0/10

---

*Generated by Agent OS Evolution Engineer*
*Date: 2026-08-31*
