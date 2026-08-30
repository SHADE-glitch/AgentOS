# Evolution Acceptance Tests

This file defines the acceptance criteria for the Phase 3.3 evolution loop.

## Test 1: Misrouting produces failure record

### Input

```text
AI 推荐系统
```

### Incorrect route

```text
llm-engineer
```

### Correct route

```text
rag-engineer
```

### Expected result

- A failure record is created in `runtime/feedback/failures/pending/` or `analyzed/`
- Error type is classified as A (Wrong Lead Skill)
- Root cause is documented
- A recommendation is recorded

## Test 2: Repeated failure triggers improvement proposal

### Input

Three route failures with the same pattern:

- RAG task routed to llm-engineer
- retrieval terms ignored by router
- no vector database guidance supplied

### Expected result

- The evolution engine generates an improvement proposal
- The proposal references runtime evidence
- The proposal includes a change recommendation for `agent-router` or the routing matrix

## Test 3: Human review gate is preserved

### Input

An improvement proposal is generated.

### Expected result

- Proposal is placed under `runtime/feedback/improvement-candidates/`
- Proposal is reviewed in `runtime/feedback/review/`
- Approval or rejection is recorded explicitly
- No skill mutation occurs before approval

## Test 4: Approved change is versioned

### Input

A proposal is approved after review.

### Expected result

- A version record is created under `skills/version-history/`
- Change reason is captured
- Evidence and benchmark result are recorded
- Status is set to tracked and reviewed

## Test 5: Benchmark validation is mandatory

### Input

A fix is proposed for routing accuracy or skill boundary drift.

### Expected result

- The validation method is recorded
- The relevant benchmark scenario is named
- The expected outcome is described
- The proposal is not marked as resolved without benchmark evidence
