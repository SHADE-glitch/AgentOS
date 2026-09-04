#!/usr/bin/env python3
"""
Audit Integration — Phase 8.9

Wires the audit layer into the existing Agent OS runtime pipeline.

This module provides non-intrusive hooks that:
  1. Record every memory retrieval event (retrieval audit)
  2. Collect pre/post task evidence (git status, diff, test output)
  3. Validate TeamResult claims against evidence

All hooks are FAIL-SAFE: exceptions are caught and logged, never blocking
the main pipeline.

Integration points:
  - loop_controller.py Stage 1 (retrieval): record_retrieval_audit()
  - loop_controller.py Stage 4/3.6 (runtime): collect_task_evidence()
  - loop_controller.py Stage 3.6 (aggregation): validate_team_result_claims()
"""

import os
import sys
import traceback

BASE = "/home/shade/.agents"
AUDIT_DIR = os.path.join(BASE, "runtime", "audit")

# Add audit dir to path for imports
if AUDIT_DIR not in sys.path:
    sys.path.insert(0, AUDIT_DIR)

from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Hook 1: Retrieval Audit ─────────────────────────────────────

def record_retrieval_audit(query, raw_result, decision_context, task_id="", loop_id="", session_id=""):
    """
    Hook: record a retrieval event to the audit log.

    Call this from loop_controller.py after retrieval_adapt() returns.

    Args:
        query: dict — task classification result
        raw_result: dict — raw retrieval result
        decision_context: dict — full DecisionContext
        task_id: str
        loop_id: str
        session_id: str — Phase 10.5: unified session ID
    """
    try:
        from retrieval_audit import record_retrieval
        record_retrieval(query, raw_result, decision_context, task_id=task_id, loop_id=loop_id, session_id=session_id)
    except Exception:
        print(f"  [audit] retrieval audit failed (non-critical): {traceback.format_exc()}")


# ── Hook 2: Evidence Collection ─────────────────────────────────

def collect_task_evidence_before(task_id, project_root=None, loop_id="", session_id=""):
    """
    Hook: collect pre-task evidence.

    Call this from loop_controller.py before task execution.

    Returns:
        dict — before evidence (or empty dict on failure)
    """
    try:
        from evidence_collector import collect_before
        return collect_before(task_id, project_root=project_root, loop_id=loop_id, session_id=session_id)
    except Exception:
        print(f"  [audit] evidence before failed (non-critical): {traceback.format_exc()}")
        return {}


def collect_task_evidence_after(task_id, before_evidence, project_root=None, loop_id="",
                                test_command="", test_stdout="", test_stderr="", test_exit_code=None,
                                session_id=""):
    """
    Hook: collect post-task evidence and save the bundle.

    Call this from loop_controller.py after task execution completes.

    Returns:
        str — path to evidence file (or empty string on failure)
    """
    try:
        from evidence_collector import collect_after, save_evidence
        after = collect_after(
            task_id, before_evidence,
            project_root=project_root, loop_id=loop_id,
            test_command=test_command, test_stdout=test_stdout,
            test_stderr=test_stderr, test_exit_code=test_exit_code,
            session_id=session_id,
        )
        path = save_evidence(task_id, before_evidence, after, session_id=session_id)
        return path
    except Exception:
        print(f"  [audit] evidence after failed (non-critical): {traceback.format_exc()}")
        return ""


# ── Hook 3: TeamResult Validation ───────────────────────────────

def validate_team_result_claims(team_result, task_id="", loop_id="", session_id=""):
    """
    Hook: validate TeamResult claims against evidence.

    Call this from loop_controller.py after team aggregation.

    Returns:
        dict — validation result (or empty dict on failure)
    """
    try:
        from team_result_validator import validate_team_result, save_validation_result
        result = validate_team_result(team_result, task_id=task_id, loop_id=loop_id, session_id=session_id)
        save_validation_result(result, session_id=session_id)
        return result
    except Exception:
        print(f"  [audit] team result validation failed (non-critical): {traceback.format_exc()}")
        return {}


# ── Convenience: Run all hooks for a single loop ─────────────────

def run_audit_hooks(loop_state, decision_context=None, team_result=None,
                    project_root=None, test_command="", test_exit_code=None):
    """
    Run all applicable audit hooks for a single loop execution.

    This is a convenience wrapper that can be called once per loop.

    Args:
        loop_state: dict — the loop state from loop_controller
        decision_context: dict — optional, from retrieval stage
        team_result: dict — optional, from collaboration stage
        project_root: str — optional, project directory
        test_command: str — optional, test command that was run
        test_exit_code: int — optional, test exit code
    """
    task_id = loop_state.get("task_id", "")
    loop_id = loop_state.get("loop_id", "")

    results = {
        "loop_id": loop_id,
        "task_id": task_id,
        "timestamp": _now_iso(),
        "retrieval_audit": None,
        "evidence_before": None,
        "evidence_after": None,
        "team_result_validation": None,
    }

    # Retrieval audit
    if decision_context:
        try:
            from retrieval_audit import get_retrieval_stats
            stats = get_retrieval_stats()
            results["retrieval_audit"] = stats
        except Exception:
            pass

    # Evidence collection (before is already done, after should be done)
    if project_root:
        try:
            from evidence_collector import get_evidence
            ev = get_evidence(task_id)
            if ev:
                results["evidence_before"] = ev.get("before", {}).get("timestamp", "")
                results["evidence_after"] = ev.get("after", {}).get("timestamp", "")
        except Exception:
            pass

    # TeamResult validation
    if team_result:
        try:
            from team_result_validator import get_validation_report
            report = get_validation_report()
            if report and report.get("validations"):
                last = report["validations"][-1]
                results["team_result_validation"] = {
                    "valid": last.get("valid", False),
                    "issues": last.get("issues", []),
                }
        except Exception:
            pass

    return results


# ── Hook 4: Provenance Generation ────────────────────────────────

def generate_provenance_artifact(task_id="", loop_id="", project_root=None, session_id=""):
    """
    Hook: generate provenance artifacts for all modified files in the project.

    Phase 10.5 (M-1): Integrates the standalone provenance_generator into the
    pipeline, so agents no longer need to manually cite line numbers.

    Args:
        task_id: str — task identifier
        loop_id: str — loop execution identifier
        project_root: str — project directory to scan
        session_id: str — Phase 10.5: unified session ID

    Returns:
        str — path to provenance artifact file (or empty string on failure)
    """
    try:
        import json
        import os as _os
        from provenance_generator import provenance_for_directory

        if not project_root or not _os.path.isdir(project_root):
            print(f"  [provenance] No valid project_root, skipping")
            return ""

        results = provenance_for_directory(project_root)
        if not results:
            print(f"  [provenance] No provenance data found in {project_root}")
            return ""

        # Save to session dir
        from evidence_collector import _session_dir
        session_dir = _session_dir(session_id)
        artifact_path = os.path.join(session_dir, f"provenance-{task_id}.json")

        artifact = {
            "task_id": task_id,
            "loop_id": loop_id,
            "generated_at": _now_iso(),
            "project_root": project_root,
            "file_count": len(results),
            "files": results,
        }
        with open(artifact_path, "w") as f:
            json.dump(artifact, f, indent=2, default=str)

        print(f"  [provenance] Saved {len(results)} file provenance(s) to {artifact_path}")
        return artifact_path
    except Exception:
        print(f"  [provenance] Failed (non-critical): {traceback.format_exc()}")
        return ""


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Usage: python3 audit_integration.py <command> [args...]")
        print("Commands: stats, validate <team_result_file> <task_id>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        try:
            from retrieval_audit import get_retrieval_stats
            stats = get_retrieval_stats()
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error: {e}")

    elif cmd == "validate":
        tr_path = sys.argv[2] if len(sys.argv) > 2 else ""
        task_id = sys.argv[3] if len(sys.argv) > 3 else ""
        if not tr_path:
            print("Error: team result file path required")
            sys.exit(1)
        import yaml
        with open(tr_path) as f:
            tr = yaml.safe_load(f)
        result = validate_team_result_claims(tr, task_id=task_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))