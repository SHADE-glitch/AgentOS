# Failure Patterns — AIView Refactoring

## Pattern FP-001: Competing RabbitMQ Consumers

### Description
Two Spring beans listen to the same RabbitMQ queue without conditional injection, causing message competition.

### Detection Method
```bash
grep -r "@RabbitListener" --include="*.java" | grep -v "@ConditionalOnProperty"
```

### Root Cause
Agent skipped interface abstraction layer, created multiple implementations without proper isolation.

### Impact
- Unpredictable scoring behavior
- Random AI/rule score alternation
- Production system instability

### Prevention Rule
**Always check for competing consumers when:**
1. Creating new @RabbitListener implementations
2. Adding @ConditionalOnProperty to existing listeners
3. Refactoring message-driven services

### Fix Template
```java
@ConditionalOnProperty(name = "app.interview.mode", havingValue = "ai")
@Service
public class AiScoringService implements ScoringService {
    // ...
}

@ConditionalOnProperty(name = "app.interview.mode", havingValue = "rule")
@Service
public class RuleBasedScoringService implements ScoringService {
    // ...
}
```

---

## Pattern FP-002: Plan-Code Gap (Interface Skip)

### Description
Agent designs interfaces in planning phase but creates concrete @Service classes in implementation.

### Detection Method
```bash
# Compare REFACTORING_PLAN.md interfaces with actual @Service classes
grep -A5 "interface.*Generator\|interface.*Evaluator\|interface.*Scorer\|interface.*Retriever" REFACTORING_PLAN.md
grep -r "@Service" --include="*.java" interview/service/
```

### Root Cause
- Agent optimizes for speed over design quality
- No validation checkpoint between planning and implementation
- Missing "interface-first" enforcement rule

### Impact
- Cannot swap implementations at runtime
- Testing requires mocking concrete classes
- Future changes require modifying existing code

### Prevention Rule
**Enforce interface-first approach:**
1. Create interface file first
2. Verify interface exists before creating implementation
3. Run `mvn compile` to validate interface contracts

---

## Pattern FP-003: Cross-Stack Output Contamination

### Description
Agent generates code in wrong technology stack (Python for Java project).

### Detection Method
```bash
# Check for Python imports in Java project
grep -r "import langchain\|import sentence_transformers\|from transformers" --include="*.java"
```

### Root Cause
- Agent lacks project context awareness
- Default training data favors Python ecosystem
- No tech stack detection before code generation

### Impact
- Useless output requiring complete rewrite
- Wasted tokens and time
- User frustration

### Prevention Rule
**Before generating code:**
1. Detect project tech stack from pom.xml/package.json/build.gradle
2. Load relevant knowledge base (java/, spring/, etc.)
3. Explicitly state "Generating Java/Spring Boot code" in output

---

## Pattern FP-004: Incomplete Dependency Isolation

### Description
Refactored code leaves dependencies on removed/conditional components without protection.

### Detection Method
```bash
# Find beans with direct AI dependencies without conditional injection
grep -r "ChatClient\|EmbeddingClient\|AiProperties" --include="*.java" | grep -v "@ConditionalOnProperty" | grep -v "legacy/"
```

### Root Cause
- Agent focuses on main flow, neglects edge cases
- No systematic dependency audit after refactoring
- Missing "conditional isolation" checklist

### Impact
- Runtime failures in specific modes
- Hidden bugs that surface in production
- Incomplete decoupling

### Prevention Rule
**After refactoring, verify:**
1. All AI-dependent beans have @ConditionalOnProperty
2. All conditional beans implement a common interface
3. Default mode (rule) can start without AI dependencies

---

## Pattern FP-005: JSON Construction via String Concatenation

### Description
Agent builds JSON responses using StringBuilder instead of proper serialization.

### Detection Method
```bash
grep -r "StringBuilder.*append.*{" --include="*.java"
grep -r "append.*\"\\{" --include="*.java"
```

### Root Cause
- Agent optimizes for simplicity over correctness
- No ObjectMapper usage enforcement
- Missing JSON construction best practices

### Impact
- Special character escaping issues
- Format errors with nested objects
- Maintenance nightmare

### Prevention Rule
**Always use:**
```java
// Good
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(report);

// Bad
String json = "{\"score\": " + score + ", \"feedback\": \"" + feedback + "\"}";
```

---

## Pattern FP-006: Missing Test Coverage

### Description
Agent creates new services without corresponding unit tests.

### Detection Method
```bash
# Compare service files with test files
find src/main -name "*Service.java" | sed 's|src/main|src/test|' | sed 's|\.java|.java|'
```

### Root Cause
- Agent prioritizes feature delivery over quality
- No test-first enforcement
- Missing test generation prompts

### Impact
- Regressions go undetected
- Refactoring becomes risky
- Technical debt accumulates

### Prevention Rule
**For every new @Service class:**
1. Create corresponding *Test.java file
2. Add at least one test method
3. Run `mvn test` to verify

---

## Meta-Patterns

### MP-001: Speed vs Quality Trade-off
- **Observation**: Agent consistently prioritizes speed over design quality
- **Evidence**: Interface skip, missing tests, string concatenation
- **Countermeasure**: Add quality checkpoints in workflow

### MP-002: Planning-Implementation Disconnect
- **Observation**: High-quality plans, poor implementation adherence
- **Evidence**: 55% plan adherence score
- **Countermeasure**: Add plan validation step before coding

### MP-003: Context Loss in Multi-Phase Tasks
- **Observation**: Agent loses project context between phases
- **Evidence**: Cross-stack output, missing dependencies
- **Countermeasure**: Maintain explicit tech stack context

---

*Generated by Agent OS Evolution Engineer*
*Date: 2026-08-31*
