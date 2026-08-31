# Phase 5.8.2.2.1 — Loop Controller Audit & Design

**Date**: 2026-08-31
**Phase**: 5.8.2.2.1
**Status**: DESIGN COMPLETE

---

## 1. Executive Summary

```yaml
can_reuse_existing_components: yes
required_new_adapter:
  - retrieval_adapter.py
  - runtime_adapter.py
required_new_code:
  - loop_controller.py (main pipeline)
  - collector.py refactoring (expose callable function)
  - validator.py refactoring (expose callable function)
  - collector_state.yaml (tracking file)
risk: medium
```

---

## 2. Component Audit Results

### 2.1 retrieval_optimizer.py

| Property | Value |
|----------|-------|
| **Path** | `runtime/memory-feedback/retrieval/retrieval_optimizer.py` |
| **Reusable function** | `retrieve(query, decay_factors=None)` |
| **Can be imported** | Yes — function is side-effect-free, returns dict |
| **CLI mode** | `main()` runs 10 hardcoded test tasks |
| **Input** | `query: dict` with keys: `task_text`, `category`, `domains`, `roles`, `keywords`, `difficulty`, `exclude_hypothesis`, `exclude_memories` |
| **Output** | `dict` with keys: `query`, `timestamp`, `total_considered`, `after_filter`, `top_k`, `results` |
| **Results schema** | `[{memory_id, static_relevance, success_rate, confidence_score, performance_gain, adaptive_score, decay_factor, final_score, evidence_level, confidence, type, category, tags, usage_count, is_hypothesis, warning, match_reasons}]` |
| **Dependencies (files)** | `retrieval-index.yaml`, `effectiveness-results.yaml`, `traces/*.yaml` |
| **Dependencies (code)** | `yaml`, `os`, `re`, `datetime`, `collections.OrderedDict` |
| **Side effects** | `_ensure_reconciled()` calls `memory_state_reconciler.py --check` via subprocess before retrieval |
| **History tracking** | `save_retrieval_history(query, result)` writes to `retrieval-history.yaml` |
| **Reusability verdict** | `retrieve()` is directly importable. No wrapper needed. |

### 2.2 Runtime Executor (OpenCode CLI)

| Property | Value |
|----------|-------|
| **Path** | `runtime/executor/` |
| **Python module** | None — conceptual adapter only |
| **Actual invocation** | `opencode run --format json --auto --model <model> '<prompt>'` |
| **Output format** | JSONL (one JSON object per line), includes `sessionID`, `text`, `tokens`, `cost` |
| **Timeout** | 120s (per `opencode-adapter.md`) |
| **Models** | `opencode/ling-3.0-flash-fin-free` (default), + 5 other free models |
| **Reusability verdict** | Must be called via `subprocess.run()`. No existing Python wrapper. |

### 2.3 collector.py

| Property | Value |
|----------|-------|
| **Path** | `runtime/memory-feedback/collector/collector.py` |
| **Reusable function** | None — only `main()` |
| **CLI mode** | `python3 collector.py` (no args) |
| **Hardcoded dependency** | `TARGET_EXECUTIONS = [...]` — 7 execution IDs hardcoded |
| **Input** | `runtime/traces/<execution_id>.yaml` (from hardcoded list) |
| **Output** | `runtime/memory-feedback/memory-candidates.yaml` |
| **Key internal functions** | `load_trace(eid)`, `validate_trace(trace)`, `evaluate_quality(response)`, `generate_candidates(trace, quality)` |
| **Reusability verdict** | `generate_candidates()` can be extracted. Needs `collect_from_traces(trace_ids)` wrapper. Must remove hardcoded `TARGET_EXECUTIONS`. |

### 2.4 validator.py

| Property | Value |
|----------|-------|
| **Path** | `runtime/memory-feedback/promotion/validator.py` |
| **Reusable function** | None — only `main()` |
| **CLI mode** | `python3 validator.py` (no args) |
| **Input** | `runtime/memory-feedback/memory-candidates.yaml` |
| **Output** | `runtime/memory-feedback/promotion/validation-results.yaml` |
| **Key internal functions** | `load_candidates()`, `load_memory_index()`, `group_candidates_by_memory(candidates)`, `validate_memory_group(memory_id, group)` |
| **Reusability verdict** | `validate_memory_group()` is callable. Needs `validate_candidates(candidates)` wrapper. |

### 2.5 promoter.py

| Property | Value |
|----------|-------|
| **Path** | `runtime/memory-feedback/promotion/promoter.py` |
| **Reusable function** | `promote_validated(validated_result)` — takes single validated dict, returns promotion result dict |
| **Can be imported** | Yes — function exists and is importable |
| **CLI mode** | `main()` — reads validation-results.yaml, promotes top 5 |
| **Input** | Single validated result dict from validator |
| **Output** | Promotion result dict with `status`, `evidence_updates`, `confidence_updates` |
| **Side effects** | Writes to `memory/*.md` frontmatter, calls `memory_state_reconciler.py --repair` via subprocess |
| **MAX_PROMOTIONS** | 5 per cycle |
| **Reusability verdict** | `promote_validated()` is directly importable. No wrapper needed. |

### 2.6 memory_state_reconciler.py

| Property | Value |
|----------|-------|
| **Path** | `runtime/memory-feedback/retrieval/memory_state_reconciler.py` |
| **Reusable function** | `check_consistency()` returns dict, `repair_index()` returns changes list |
| **Can be imported** | Yes — functions are importable |
| **CLI mode** | `python3 memory_state_reconciler.py --check` or `--repair` |
| **Input** | `memory/retrieval-index.yaml` + `memory/*/*.md` |
| **Output** | `--check`: prints "CONSISTENT" or "INCONSISTENT" + drifts; `--repair`: updates `retrieval-index.yaml` |
| **Reusability verdict** | Importable functions exist. Also callable via subprocess. |

---

## 3. Breakpoint Analysis

### Breakpoint 1: Retrieval → Runtime

```yaml
current_state:
  - retrieval_optimizer.retrieve() exists and is importable
  - No code calls it before invoking OpenCode CLI
  - Traces contain manually crafted memory_retrieval sections
  
root_cause:
  - No pipeline controller exists
  - No retrieval → prompt construction step
  - No programmatic OpenCode invocation

fix:
  - Create retrieval_adapter.py: task → retrieve() → Decision Context YAML
  - Create runtime_adapter.py: Decision Context + task → OpenCode CLI → trace YAML
  - Loop controller calls both sequentially
```

### Breakpoint 2: Runtime → Collector

```yaml
current_state:
  - collector.py has hardcoded TARGET_EXECUTIONS list
  - New traces from loop controller would NOT be picked up
  - No mechanism to track which traces have been processed

root_cause:
  - collector.py designed for batch processing, not incremental
  - No collector_state.yaml to track processed traces

fix:
  - Refactor collector.py: expose collect(trace_ids) or collect_new_traces()
  - Create collector_state.yaml: tracks processed trace_ids + last_scan timestamp
  - Loop controller passes trace_id to collector after each execution
```

### Breakpoint 3: Feedback → Promotion → Reconciler → Retrieval

```yaml
current_state:
  - collector, validator, promoter, reconciler are all independent CLI tools
  - Only promoter calls reconciler via subprocess (after promotion)
  - No sequential pipeline exists

root_cause:
  - Each component has its own main() but no shared orchestration interface
  - No pipeline controller

fix:
  - Create loop_controller.py: calls all stages sequentially
  - Each stage returns structured result; controller checks status before proceeding
  - Controller maintains loop state in state/<loop_id>.yaml
```

---

## 4. Required New Components

### 4.1 retrieval_adapter.py

**Purpose**: Bridge between task input and retrieval_optimizer output.

```yaml
location: runtime/loop-controller/retrieval_adapter.py
callable: adapt(task_id, task_text, memory_mode) → DecisionContext

input:
  task_id: str
  task_text: str
  memory_mode: "enabled" | "fallback" | "disabled"

output (DecisionContext):
  retrieval_context:
    memories: [...]          # Top-K from retrieval_optimizer
    ranking: [...]           # sorted by final_score
    evidence: [...]          # evidence_level per memory
    confidence: [...]        # confidence_score per memory
    applicability: [...]     # match_reasons per memory
    hypotheses: [...]        # separated from facts
    total_retrieved: int
    filter_applied: bool
```

**Implementation strategy**: Import `retrieve()` from `retrieval_optimizer`. Classify task, construct query dict, call retrieve, format output.

### 4.2 runtime_adapter.py

**Purpose**: Bridge between DecisionContext and OpenCode CLI invocation.

```yaml
location: runtime/loop-controller/runtime_adapter.py
callable: execute(task_id, task_text, decision_context, model) → ExecutionResult

input:
  task_id: str
  task_text: str
  decision_context: DecisionContext (from retrieval_adapter)
  model: str (e.g. "opencode/ling-3.0-flash-fin-free")

output (ExecutionResult):
  execution_id: str
  trace_id: str
  session_id: str
  provider: str
  model: str
  start_time: ISO8601
  end_time: ISO8601
  latency_ms: int
  token_usage: {input, output, total}
  output_hash: str
  final_output: str
  status: "success" | "error" | "timeout"
  trace_file: str
```

**Implementation strategy**: Construct prompt with memory context, call `opencode run` via subprocess, parse JSONL output, write trace YAML to `runtime/traces/`.

### 4.3 loop_controller.py

**Purpose**: Main pipeline controller that calls all stages sequentially.

```yaml
location: runtime/loop-controller/loop_controller.py
callable: run_loop(task_id, task_text, memory_mode, model) → LoopResult

pipeline:
  1. retrieval_adapter.adapt()       → DecisionContext
  2. runtime_adapter.execute()        → ExecutionResult + trace
  3. collector.collect([trace_id])    → [Candidate]
  4. validator.validate(candidates)   → [ValidationResult]
  5. promoter.promote(validated)      → [PromotionResult]
  6. reconciler.check_consistency()   → CONSISTENT | INCONSISTENT
  7. reconciler.repair_index()        → (if inconsistent)
  8. save loop state

failure_handling:
  - Any stage failure → loop_status = "failed"
  - Memory failure → fallback to baseline runtime (skip memory injection)
  - Trace missing → skip collector, log warning
  - Validation/Promotion failure → skip downstream, preserve state

idempotency:
  - same loop_id → skip if already completed
  - same trace_id → skip collector (already processed)
```

### 4.4 collector.py Refactoring

**Required changes**:

```yaml
add:
  - function: collect_from_trace_ids(trace_ids: list[str]) → list[Candidate]
  - function: collect_new_traces() → list[Candidate]  # reads collector_state.yaml
  - file: collector_state.yaml  # tracks processed traces

modify:
  - Remove hardcoded TARGET_EXECUTIONS from main()
  - main() reads from collector_state.yaml or accepts CLI args

keep:
  - load_trace(), validate_trace(), evaluate_quality(), generate_candidates()
  - All candidate generation rules R1-R6
```

### 4.5 validator.py Refactoring

**Required changes**:

```yaml
add:
  - function: validate_candidates(candidates: list[dict]) → list[ValidationResult]
  - Accepts candidates list directly, not just from file

modify:
  - main() becomes a thin wrapper around validate_candidates()

keep:
  - group_candidates_by_memory(), validate_memory_group()
  - All validation rules and thresholds
```

### 4.6 collector_state.yaml

```yaml
location: runtime/loop-controller/state/collector_state.yaml

schema:
  version: "1.0"
  last_scan: ISO8601
  processed_traces:
    - trace_id: str
      processed_at: ISO8601
      candidates_generated: int
```

---

## 5. Component Interface Summary

| Component | Importable? | Callable Function | Refactoring Needed |
|-----------|------------|-------------------|-------------------|
| retrieval_optimizer | Yes | `retrieve(query, decay_factors)` | None |
| Runtime (OpenCode) | No (subprocess) | `opencode run ...` | New adapter |
| collector | No | `generate_candidates(trace, quality)` | Add `collect_from_trace_ids()` |
| validator | No | `validate_memory_group(mid, group)` | Add `validate_candidates()` |
| promoter | Yes | `promote_validated(result)` | None |
| reconciler | Yes | `check_consistency()`, `repair_index()` | None |

---

## 6. Data Flow Diagram

```
Task Input
  │
  ▼
retrieval_adapter.py
  │  import retrieval_optimizer.retrieve()
  │  classify task, query retrieval
  ▼
DecisionContext (dict)
  │  memories, ranking, evidence, hypotheses
  ▼
runtime_adapter.py
  │  construct prompt with memory context
  │  subprocess: opencode run --format json --auto --model <model> '<prompt>'
  │  parse JSONL, capture tokens/latency/output
  │  write trace to runtime/traces/<execution_id>.yaml
  ▼
ExecutionResult (dict)
  │  execution_id, trace_id, session_id, tokens, latency, output_hash, final_output
  ▼
collector.py (refactored)
  │  collect_from_trace_ids([trace_id])
  │  load trace, validate, evaluate quality, generate candidates
  ▼
[Candidate] (list)
  │  candidate_id, source_execution, target_memory, candidate_type, quality_score
  ▼
validator.py (refactored)
  │  validate_candidates(candidates)
  │  group by memory_id, check gates M1-M6
  ▼
[ValidationResult] (list)
  │  memory_id, status (validated|rejected|hold), confidence, rejection_reason
  ▼
promoter.py
  │  promote_validated(validated_result) for each validated
  │  update memory/*.md frontmatter
  │  subprocess: memory_state_reconciler.py --repair
  ▼
[PromotionResult] (list)
  │  memory_id, status (applied|rejected), evidence_updates, confidence_updates
  ▼
memory_state_reconciler.py
  │  check_consistency() → CONSISTENT | INCONSISTENT
  ▼
Loop State
  │  state/<loop_id>.yaml
  └── loop_id, current_stage, all IDs, errors, timestamps
```

---

## 7. File Structure

```
runtime/loop-controller/
├── loop_controller.py              # Main pipeline controller
├── retrieval_adapter.py            # Retrieval → DecisionContext
├── runtime_adapter.py              # DecisionContext → OpenCode → Trace
├── execution-contract.yaml         # Loop execution contract
└── state/
    ├── collector_state.yaml        # Trace processing tracker
    └── <loop_id>.yaml             # Per-loop state
```

---

## 8. Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| OpenCode CLI may fail silently | Medium | Parse JSONL for error indicators, enforce timeout |
| Subprocess overhead per call | Low | OpenCode is already a subprocess; acceptable |
| Trace format mismatch with collector | Low | Runtime adapter writes traces in existing format |
| Collector hardcoded paths break after refactoring | Medium | Keep backward-compatible paths, add configurable base |
| Promoter writes to .md files mid-loop | High | Only promote after successful validation; never modify canonical content |
| Loop state corruption on partial failure | Medium | Atomic writes to state files, append-only logs |
| Idempotency violation | Medium | Check loop_id + trace_id before each stage |

---

## 9. Acceptance Criteria for Implementation

Only proceed to implementation after this design is approved:

```yaml
pre_implementation_checks:
  - "Design document reviewed"
  - "All 6 component interfaces confirmed"
  - "Refactoring scope agreed"
  - "File structure agreed"
  - "Risk mitigations accepted"

implementation_acceptance:
  retrieval_to_runtime: "PASS when retrieval_adapter → runtime_adapter chain works"
  runtime_to_trace: "PASS when trace is generated programmatically, not manually"
  trace_to_collector: "PASS when collector picks up new trace without hardcoded list"
  collector_to_validator: "PASS when validator receives candidates from collector"
  validator_to_promoter: "PASS when only validated candidates reach promoter"
  promoter_to_reconciler: "PASS when reconciler reports CONSISTENT after promotion"
  reconciler_to_retrieval: "PASS when next retrieval sees updated index"
  fallback: "PASS when memory failure → baseline runtime continues"
  idempotency: "PASS when same loop_id → no duplicate promotion"
  provenance: "PASS when every memory_id has traceable execution path"
```

---

## 10. Decision

```yaml
decision: "DESIGN COMPLETE — AWAIT APPROVAL"
next_step: "Phase 5.8.2.2.2 — Implementation"
blockers: []
notes: |
  - All 6 components have reusable interfaces (3 importable, 3 need minor refactoring)
  - 2 new adapters needed (retrieval_adapter.py, runtime_adapter.py)
  - 1 new controller needed (loop_controller.py)
  - 2 existing files need refactoring (collector.py, validator.py)
  - 1 new state file needed (collector_state.yaml)
  - Risk is medium due to OpenCode subprocess dependency and .md write-back
  - Do NOT implement until design is approved
```