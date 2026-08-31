# Memory Retrieval Protocol

**Phase**: 5.3
**Version**: 1.0
**Status**: active

---

## 1. Purpose

This protocol defines how Agent OS retrieves Engineering Memory to support task routing and orchestration decisions. It is a deterministic, explainable, metadata-driven retrieval system — not a black-box similarity engine.

---

## 2. Query Contract

### 2.1 Query Input

```yaml
query:
  task_text: "<natural language task description>"
  category: "<architecture|backend|ai|frontend|optimization|cross-cutting>"
  difficulty: "<easy|medium|hard>"
  domains: ["<domain1>", "<domain2>"]
  roles: ["<role1>", "<role2>"]
  keywords: ["<keyword1>", "<keyword2>"]
```

### 2.2 Query Output

```yaml
retrieval_result:
  memories:
    - memory_id: "<id>"
      type: "<task|failure|success|pattern|anti-pattern|effectiveness|hypothesis>"
      category: "<category>"
      relevance_score: <0.0-1.0>
      evidence_level: "<level>"
      evidence_weight: <0.0-1.0>
      final_score: <relevance_score * evidence_weight>
      confidence: "<low|medium|high>"
      match_reasons: ["<reason1>", "<reason2>"]
      warning: "<optional warning for hypothesis>"
```

---

## 3. Retrieval Pipeline

```text
Query Input
  ↓
1. Normalize (lowercase, strip, extract keywords)
  ↓
2. Classify (category, domains, difficulty)
  ↓
3. Candidate Selection (category filter + domain filter)
  ↓
4. Metadata Filter (exclude deprecated, status filter)
  ↓
5. Relevance Scoring (category + domain + type + tags + keyword)
  ↓
6. Evidence Weighting (evidence_level → weight multiplier)
  ↓
7. Hypothesis Flagging (type=hypothesis → warning)
  ↓
8. Top-K Selection (k=5, sorted by final_score desc)
  ↓
9. Deduplication (same source → keep highest score)
  ↓
10. Context Formatting
  ↓
Output
```

---

## 4. Relevance Scoring

### 4.1 Score Components

| signal | weight | description |
|--------|--------|-------------|
| category_match | 0.25 | query.category == memory.category |
| domain_match | 0.20 | overlap(query.domains, memory.tags) / max(len(query.domains), 1) |
| type_boost | 0.15 | bonus for failure/anti-pattern when query is high-risk domain |
| role_match | 0.15 | overlap(query.roles, memory.tags) / max(len(query.roles), 1) |
| keyword_match | 0.10 | overlap(query.keywords, memory.tags) / max(len(query.keywords), 1) |
| difficulty_match | 0.10 | query.difficulty present in memory source tasks |
| tag_overlap | 0.05 | raw tag overlap beyond domain/role/keyword signals |

### 4.2 Type Boost

| memory type | boost condition |
|-------------|----------------|
| failure | +0.15 if query.domains includes the failure domain (learn from past mistakes) |
| anti-pattern | +0.15 if query task appears single-domain (prevent team inflation) |
| pattern | +0.05 if query.domains >= 2 (cross-domain is pattern's sweet spot) |
| hypothesis | -0.00 (no boost, handled separately in Step 7) |

### 4.3 Example

```yaml
query:
  category: "backend"
  domains: ["payment", "security"]
  roles: ["backend-architect", "security-engineer"]
  keywords: ["pci-dss", "compliance"]

memory: T-004 (payment-system)
  - category_match: 0.25 (backend == backend)
  - domain_match: 0.20 (2/2 domains match tags)
  - type_boost: 0.00 (task, no boost)
  - role_match: 0.15 (2/2 roles match)
  - keyword_match: 0.10 (2/2 keywords match)
  - difficulty_match: 0.00 (no difficulty in query)
  - tag_overlap: 0.05 (tags overlap)
  relevance_score: 0.75
```

---

## 5. Evidence Weighting

### 5.1 Weights

| evidence_level | weight | description |
|----------------|--------|-------------|
| `hypothesis` | 0.3 | Untested, purely speculative |
| `benchmark_evaluated` | 0.6 | Observed in benchmark execution (Round 0) |
| `independent_validated` | 0.8 | Confirmed by multiple independent benchmarks |
| `real_project_validated` | 0.95 | Confirmed in real (non-production) project |
| `production_validated` | 1.0 | Confirmed in real production system |

### 5.2 Final Score

```text
final_score = relevance_score × evidence_weight
```

### 5.3 Example

```yaml
memory: T-004 (payment-system)
  relevance_score: 0.75
  evidence_level: benchmark_evaluated
  evidence_weight: 0.60
  final_score: 0.45
```

---

## 6. Hypothesis Isolation

### 6.1 Rule

All memories with `type: hypothesis` MUST be flagged with:

```yaml
warning: "Unvalidated hypothesis — not an established engineering rule"
```

### 6.2 Handling

- Hypothesis memories are retrieved normally (participate in ranking)
- But they are ALWAYS marked with the warning
- Hypothesis contamination rate = (hypothesis retrieved without warning) / total retrieved
- **Target: contamination rate = 0**

### 6.3 Example

```yaml
- memory_id: "H-001"
  type: "hypothesis"
  final_score: 0.42
  warning: "Unvalidated hypothesis — not an established engineering rule"
  match_reasons: ["category=backend", "tags=cost-delta"]
```

---

## 7. Failure / Conflict Priority

### 7.1 Rule

When a query domain matches a known failure domain, the failure memory gets a `type_boost` of +0.15.

### 7.2 Rationale

Avoiding past failures is more valuable than repeating past successes. Failure memories should rank higher when the current task is similar to a past failure.

### 7.3 Example

```yaml
query:
  domains: ["payment", "security"]

memory: F-002 (card-data-conflict)
  type_boost: +0.15 (failure + domain match)
  → ranked higher than T-004 (task memory of same domain)
```

---

## 8. Top-K Selection

### 8.1 Parameters

```yaml
k: 5
min_score: 0.0
sort: final_score desc
```

### 8.2 Memory Type Distribution

Target distribution in top-k (soft constraint, not enforced):

| type | target fraction |
|------|----------------|
| pattern | 0.2 |
| failure | 0.2 |
| success | 0.2 |
| task | 0.2 |
| hypothesis | 0.1 |
| anti-pattern | 0.1 |

### 8.3 Deduplication

If two memories share the same source task(s), keep only the highest-scoring one.

---

## 9. Context Formatting

### 9.1 Output Format

Every retrieved memory injected into Agent context must include:

```markdown
**Historical Engineering Memory**

- **Memory**: {title}
- **Type**: {type}
- **Evidence Level**: {evidence_level}
- **Confidence**: {confidence}
- **Relevance**: {relevance_score}
- **Source**: {source.task_id} (Round 0)
- **Why Retrieved**: {match_reasons}
- **Warning**: {warning if hypothesis}

**Summary**: {first 3 sentences of memory body}

**Limitations**: {evidence limitations, sample size}
```

### 9.2 Anti-Pattern

Do NOT inject:

```text
"Multi-Agent is better"
```

Instead inject:

```markdown
**Historical Engineering Memory**

- **Memory**: P-001 Cross-Domain Specialist Collaboration
- **Type**: pattern
- **Evidence Level**: benchmark_evaluated
- **Confidence**: low
- **Relevance**: 0.84

**Why Retrieved**: category=architecture, domain=backend, task_type=multi-domain

**Summary**: When a task spans 3+ technical domains, forming a multi-agent team
with one specialist per domain consistently produces higher quality output than
a single generalist agent. Observed in 4 tasks (arch-02, backend-01, ai-01, ai-02)
with average quality delta +1.25.

**Limitations**: Only 4 observations in Round 0 benchmark. Small sample size.
Not yet validated in real projects.
```

---

## 10. Non-Goals

This retrieval system does NOT:

- Use vector embeddings or semantic similarity
- Modify memory files
- Create new memories automatically
- Override Router or Orchestrator decisions
- Learn from retrieval patterns

---

## 11. Version History

| version | date | changes |
|---------|------|---------|
| 1.0 | 2026-08-30 | Initial protocol |

---

*Retrieval protocol defined. Ready for implementation.*