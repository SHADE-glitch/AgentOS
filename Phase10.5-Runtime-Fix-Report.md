# Phase 10.5 — Runtime Data-Link Fix Report

**Date**: 2026-09-04
**Role**: Agent OS Runtime Maintainer
**Audit Reference**: Phase 10 Pre-Benchmark Audit

---

## Summary

All 2 Blockers, 3 Major issues, and 3 Minor issues identified in the pre-benchmark audit have been addressed.

---

## Fixes Applied

### B-2 [BLOCKER] — Unified Session ID Lifecycle

**Problem**: 4 modules (retrieval_audit, evidence_collector, team_result_validator, failure_detector) each generated independent datetime-based session IDs, causing reports to scatter across different session directories.

**Fix**:
- `loop_controller.py` generates a single `session_id` at pipeline start
- `os.environ["AOS_SESSION_ID"]` is set for subprocess propagation
- All audit hooks accept `session_id` parameter, passed from loop_controller
- All recovery modules accept `session_id` parameter
- Underlying modules use `session_id or _session_id()` pattern — explicit session_id takes priority

**Modified files**:
- `loop_controller.py` — session_id generation, init_loop_state, all hook calls
- `audit_integration.py` — all 3 hooks + convenience function
- `retrieval_audit.py` — record_retrieval()
- `evidence_collector.py` — collect_before(), collect_after(), save_evidence()
- `team_result_validator.py` — validate_team_result(), save_validation_result()
- `failure_detector.py` — detect_failures()
- `recovery_integration.py` — run_recovery_loop()
- `retry_controller.py` — record_retry_attempt(), get_retry_count(), get_retry_history(), execute_retry_loop()

**Verification**: Dry-run confirms all 3+ report files in same `reports/{session}/` directory.
```
reports/SESS-20260904-011027/
  evidence-DRYRUN-002.json
  provenance-DRYRUN-002.json
  team-result-validation.json
```

---

### B-1 [BLOCKER] — Test Evidence Data Chain

**Problem**: `runtime_adapter.execute()` returned no `test_command`, `test_exit_code`, `test_stdout`, `test_stderr` fields. Evidence collector read empty values, so "tested" claim validation always failed and `failed_tests` detection never triggered.

**Fix**:
- Added `collect_test_evidence_from_project()` hook in `runtime_adapter.py`
- Reads from `AOS_TEST_RESULT` env var (JSON), or `.aos_test_result.json`, or `test_output.json` in project root
- `execute()` now includes `test_command`, `test_exit_code`, `test_stdout`, `test_stderr` in return dict
- Fields default to empty/None when no test data is available — no false positives

**Modified files**:
- `runtime_adapter.py` — added `collect_test_evidence_from_project()`, extended `execute()` return dict

**Verification**: Test file injection produces correct test evidence in evidence JSON.
```
.aos_test_result.json → {"test_command":"pytest","test_exit_code":0,...}
→ evidence JSON contains test_exit_code=0
```

---

### M-1 [MAJOR] — Provenance Generator Integration

**Problem**: `provenance_generator.py` was a standalone CLI tool, never called from the pipeline. Agents had to manually cite line numbers.

**Fix**:
- Added `generate_provenance_artifact()` hook in `audit_integration.py`
- Called from loop_controller after TeamResult validation in both multi-agent and single-agent paths
- Saves `provenance-{task_id}.json` to session directory
- Failure is non-blocking (warning only)

**Modified files**:
- `audit_integration.py` — added `generate_provenance_artifact()` hook
- `loop_controller.py` — added import and call in both paths

**Verification**: Dry-run saved 69 file provenance entries.
```
provenance-DRYRUN-002.json — 69 files with git_commit, file_path, symbol info
```

---

### M-3 [MAJOR] — Single-Agent Path Validation

**Problem**: Single-agent (OpenCode) executions had no TeamResult, so validator and recovery had nothing to validate.

**Fix**:
- Single-agent path now generates a minimal TeamResult dict after evidence collection
- Includes: agent, task_id, summary, evidence, validation_context, model, provider, execution_id, trace_id, status, latency_ms, token_usage
- Goes through `validate_team_result_claims()` just like multi-agent path
- Recovery loop now receives `team_result_data` for both paths

**Modified files**:
- `loop_controller.py` — single-agent TeamResult generation + validation

---

### M-2 [MAJOR] — Recovery Decision Interface

**Problem**: Recovery was advisory-only (`retry_fn=None`) with no clear interface for future integration.

**Fix**:
- Added `RecoveryDecision` interface documentation in `recovery_integration.py` docstring
- Documents the contract: `detect → plan → record` (advisory), with `retry_fn` as future entry point
- Recovery loop now passes `team_result_data` for both paths (not just multi-agent)
- Recovery loop uses `session_id` from state for consistent session tracking

**Modified files**:
- `recovery_integration.py` — added RecoveryDecision interface doc, session_id propagation
- `loop_controller.py` — updated recovery loop call to pass session_id and team_result_data unconditionally

---

### MINOR-1 — team_result_data Initialization

**Fix**: `team_result_data = None` initialized before `if is_multi_agent:` block.

**Modified**: `loop_controller.py`

---

### MINOR-2 — Recovery State in init_loop_state

**Fix**: Added `"recovery": {...}` block to `init_loop_state()`. Recovery loop now updates existing state instead of overwriting.

**Modified**: `loop_controller.py`

---

### MINOR-3 — Benchmark Harness Structure

**Created**:
```
~/.agents/benchmark/
  baseline/          — A: Bare OpenCode test
  agent_os/          — B: Agent OS + OpenCode test
  failure_recovery/  — C: Failure recovery test
  memory_test/       — D: Memory impact test
```

---

## Data Flow: Before vs After

### Before (Phase 10):
```
Stage 1  → retrieval_audit  → reports/SESS-20260904-004600/
Stage 4  → evidence_collect → reports/SESS-20260904-004601/  ← DIFFERENT
Stage 3.6 → team_validator  → reports/SESS-20260904-004602/  ← DIFFERENT
Stage 9.5 → failure_detect  → reports/SESS-20260904-004603/  ← DIFFERENT
```

### After (Phase 10.5):
```
run_loop → session_id = "SESS-20260904-011027"
  ↓
Stage 1  → retrieval_audit(session_id)  → reports/SESS-20260904-011027/
Stage 4  → evidence_collect(session_id) → reports/SESS-20260904-011027/  ← SAME
Stage 3.6 → team_validator(session_id)  → reports/SESS-20260904-011027/  ← SAME
Stage 4*  → provenance_gen(session_id)  → reports/SESS-20260904-011027/  ← SAME
Stage 9.5 → failure_detect(session_id)  → reports/SESS-20260904-011027/  ← SAME
```

---

## Modified Files Summary

| File | Changes |
|------|---------|
| `runtime/loop-controller/loop_controller.py` | session_id generation, init_loop_state, all hook calls, single-agent TeamResult, provenance, recovery state, team_result_data init |
| `runtime/loop-controller/runtime_adapter.py` | test evidence collection hook, test fields in return dict |
| `runtime/audit/audit_integration.py` | session_id params, provenance hook (M-1) |
| `runtime/audit/retrieval_audit.py` | session_id param |
| `runtime/audit/evidence_collector.py` | session_id params |
| `runtime/audit/team_result_validator.py` | session_id params |
| `runtime/recovery/failure_detector.py` | session_id param |
| `runtime/recovery/recovery_integration.py` | RecoveryDecision interface, session_id propagation |
| `runtime/recovery/retry_controller.py` | session_id params |
| `benchmark/` | directory structure (4 dirs) |

---

## Verification Results

### Dry-run (test_provider mode):
```
session_id: SESS-20260904-011027
reports in session: [evidence-DRYRUN-002.json, provenance-DRYRUN-002.json, team-result-validation.json]
recovery: 1 failure detected, plan generated, advisory mode
provenance: 69 files
```

### Session ID propagation test:
```
retrieval_audit: OK
evidence_collector: OK (test_exit_code=0)
team_result_validator: OK (valid=True, checks=4)
failure_detector: OK (0 events)
All 3+ files in same session directory: PASS
```

### Test evidence hook test:
```
.aos_test_result.json → {"test_command":"pytest","test_exit_code":0,...}
→ collect_test_evidence_from_project() returns correct data
```

---

## Remaining Issues (pre-existing, not introduced by Phase 10.5)

1. `promote_validated()` has unexpected `loop_id` keyword argument (Stage 8 fails)
2. Code validation fails on non-standard git output (pre-existing)
3. Test provider module is not implemented (expected)

---

## Conclusion

All 2 Blockers and 3 Major issues from the Phase 10 Pre-Benchmark Audit have been resolved. The runtime data pipeline is now closed-loop with unified session tracking. The system is ready for the next stage — but **do not enter Benchmark yet** — wait for explicit instruction.