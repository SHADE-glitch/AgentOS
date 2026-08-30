# Evolution Events

## Event examples

```yaml
event_id: E-001
timestamp: 2026-08-30T15:30:00Z
event_type: "proposal_generated"
proposal_id: "IC-001"
source: "runtime failure review"
status: "approved"
reviewed_by: "human"
benchmark_reference: "runtime/datasets/benchmark/real-world-benchmark.md"

---

event_id: E-002
timestamp: 2026-08-30T15:35:00Z
event_type: "proposal_generated"
proposal_id: "IC-002"
source: "runtime failure review"
status: "approved"
reviewed_by: "human"
benchmark_reference: "runtime/metrics/router-baseline.md"

---

event_id: E-003
timestamp: 2026-08-30T15:40:00Z
event_type: "proposal_generated"
proposal_id: "IC-003"
source: "runtime failure review"
status: "reviewed"
reviewed_by: "human"
benchmark_reference: "runtime/metrics/routing-quality.md"
```

## Purpose

This record captures each proposal, review decision, and benchmark verification event in the evolution loop. The system should only progress when these events are evidence-backed and human-reviewed.
