# Memory Quality Gates (M1-M6)

Every memory entry in this system must pass these gates before being promoted to `validated` status.

## M1: Provenance Gate

**Rule**: Every memory MUST have a `source` block with at minimum:
- `type` (benchmark | real-project | observation | hypothesis)
- For benchmark-sourced memories: `task_id`, `run_id`

**Fail**: Missing source → memory cannot enter `validated` status. Mark as `status: new` until provenance is added.

**Check**: `memory.source.type` exists AND is not empty.

---

## M2: Evidence Level Gate

**Rule**: Every memory MUST declare an `evidence_level`. Default is `hypothesis` if no evidence exists.

Valid levels (ascending):
- `hypothesis` — proposed, untested
- `benchmark_evaluated` — observed in benchmark execution
- `independent_validated` — confirmed by multiple independent benchmarks
- `real_project_validated` — confirmed in real (non-production) project
- `production_validated` — confirmed in real production system

**Fail**: Missing evidence_level → memory cannot be used for routing or orchestration decisions.

**Check**: `memory.evidence_level` exists AND is in valid list.

---

## M3: Duplicate Detection Gate

**Rule**: Before creating a new memory, check for existing memories with the same `type` + `category` + similar content.

**Fail**: Duplicate found → merge or reject. Do not create a new entry.

**Check**: No existing memory with (same type, same category, overlapping tags).

---

## M4: Confidence Gate

**Rule**: Confidence must be justified by evidence count:

| confidence | min observations | max observations |
|------------|-----------------|------------------|
| `low` | 0 | 1 |
| `medium` | 2 | 4 |
| `high` | 5 | ∞ |

**Fail**: `high` confidence with < 5 observations → downgrade to `medium`.

**Check**: `memory.confidence` matches observation count.

---

## M5: Retrieval Relevance Gate

**Rule**: Memory retrieval must filter by:
- Task category match (primary filter)
- Evidence level (higher priority first)
- Status (exclude `deprecated`)

**Fail**: No relevance filter applied → memory pollution risk. Agent receives irrelevant memories.

**Check**: Retrieved memories share at least one category or tag with the current task.

---

## M6: Staleness Gate

**Rule**: Memories with `status: deprecated` must never be retrieved. Memories with `created_at > 90 days` without re-validation must be reviewed before use.

**Fail**: Stale memory used in active decision → flag for review.

**Check**: `status != deprecated` AND (`created_at` within 90 days OR `last_validated_at` within 90 days).

---

## Gate Application

| memory status | M1 | M2 | M3 | M4 | M5 | M6 |
|--------------|----|----|----|----|----|----|
| new | ⚠ soft | ⚠ soft | ✓ | — | — | — |
| observed | ✓ | ✓ | ✓ | ⚠ soft | — | — |
| validated | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| trusted | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| deprecated | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

- ✓ = hard gate (must pass)
- ⚠ soft = soft gate (warning, does not block)
- — = not applicable