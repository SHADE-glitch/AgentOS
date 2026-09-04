#!/usr/bin/env python3
"""
TeamResult Validator — Phase 8.9

Validates TeamResult claims against actual evidence artifacts.

Rules:
  1. If TeamResult claims "tested" → must have: command, exit_code, output
  2. If TeamResult claims "memory influenced" → must have: retrieval artifact
  3. If TeamResult claims "code changed" → must have: git diff evidence
  4. If TeamResult claims "reviewed" → must have: review file or diff

Output: ~/.agents/reports/{session}/team-result-validation.json

This is a POST-HOC validator. It does not modify the TeamResult.
It only produces an audit report.
"""

import os
import json
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
REPORTS_DIR = os.path.join(BASE, "reports")


def _session_id():
    return os.environ.get("AOS_SESSION_ID", datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S"))


def _session_dir(session=None):
    sid = session or _session_id()
    d = os.path.join(REPORTS_DIR, sid)
    os.makedirs(d, exist_ok=True)
    return d


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load_json(path):
    """Load a JSON file or return None."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_evidence(task_id, session=None):
    """Load evidence bundle for a task."""
    session_dir = _session_dir(session)
    path = os.path.join(session_dir, f"evidence-{task_id}.json")
    return _load_json(path)


def _has_retrieval_artifact(session=None):
    """Check if a retrieval audit artifact exists."""
    session_dir = _session_dir(session)
    path = os.path.join(session_dir, "memory-retrieval.jsonl")
    if os.path.exists(path):
        return os.path.getsize(path) > 0
    return False


def validate_team_result(team_result, session=None, task_id="", loop_id="", session_id=""):
    """
    Validate a TeamResult against evidence artifacts.

    Args:
        team_result: dict — the TeamResult data (from aggregator or team-result YAML)
        session: str — session ID (legacy)
        task_id: str — task identifier
        loop_id: str — loop execution identifier
        session_id: str — Phase 10.5: unified session ID

    Returns:
        dict with validation results: {valid: bool, checks: [...], issues: [...]}
    """
    session = session_id or session
    checks = []
    issues = []

    # Extract claims from TeamResult
    summary = ""
    if isinstance(team_result, dict):
        # Could be from aggregator.to_dict() or raw team-result YAML
        tr = team_result.get("team_result", team_result)
        if isinstance(tr, dict):
            summary = tr.get("summary", "")
            lead_output = tr.get("lead_output", {})
            if isinstance(lead_output, dict):
                output_text = lead_output.get("output", lead_output.get("summary", ""))
                if output_text:
                    summary = str(output_text) + " " + summary
        else:
            summary = str(tr)
    elif isinstance(team_result, str):
        summary = team_result

    summary_lower = summary.lower() if summary else ""

    # ── Check 1: "tested" claim ──
    _tested = any(kw in summary_lower for kw in ["tested", "test pass", "tests pass", "test result", "verified by test", "tested manually", "manual test", "test output", "ran test"])
    if _tested:
        evidence = _load_evidence(task_id, session)
        if evidence:
            after = evidence.get("after", {})
            tcmd = after.get("test_command", "")
            texit = after.get("test_exit_code")
            tstdout = after.get("test_stdout", "")

            if tcmd and texit is not None:
                checks.append({
                    "check": "tested_claim",
                    "status": "pass",
                    "detail": f"Test command '{tcmd}' found, exit_code={texit}",
                })
            elif tcmd:
                checks.append({
                    "check": "tested_claim",
                    "status": "warn",
                    "detail": f"Test command '{tcmd}' found but no exit_code recorded",
                })
                issues.append("TeamResult claims 'tested' but no test exit_code found in evidence")
            else:
                checks.append({
                    "check": "tested_claim",
                    "status": "fail",
                    "detail": "TeamResult claims 'tested' but no test_command in evidence",
                })
                issues.append("TeamResult claims 'tested' but no test_command recorded in evidence")
        else:
            checks.append({
                "check": "tested_claim",
                "status": "fail",
                "detail": "TeamResult claims 'tested' but no evidence file found",
            })
            issues.append(f"TeamResult claims 'tested' but no evidence file for task '{task_id}'")
    else:
        checks.append({
            "check": "tested_claim",
            "status": "skip",
            "detail": "No 'tested' claim in TeamResult",
        })

    # ── Check 2: "memory influenced" claim ──
    _memory_influenced = any(kw in summary_lower for kw in ["memory influenced", "memory used", "retrieved memory", "memory guidance", "memory-informed", "based on memory", "memory suggested"])
    if _memory_influenced:
        if _has_retrieval_artifact(session):
            checks.append({
                "check": "memory_influenced_claim",
                "status": "pass",
                "detail": "Retrieval audit artifact found",
            })
        else:
            checks.append({
                "check": "memory_influenced_claim",
                "status": "fail",
                "detail": "TeamResult claims 'memory influenced' but no retrieval audit artifact",
            })
            issues.append("TeamResult claims 'memory influenced' but no memory-retrieval.jsonl found")
    else:
        checks.append({
            "check": "memory_influenced_claim",
            "status": "skip",
            "detail": "No 'memory influenced' claim in TeamResult",
        })

    # ── Check 3: "code changed" / "modified" claim ──
    _code_changed = any(kw in summary_lower for kw in ["code changed", "modified file", "edited file", "created file", "deleted file", "changed file", "updated file", "file changed", "code modified", "implemented", "refactored"])
    if _code_changed:
        evidence = _load_evidence(task_id, session)
        if evidence:
            after = evidence.get("after", {})
            files_changed = after.get("files_changed", [])
            new_files = after.get("new_files", [])
            diff_stat = after.get("diff_stat", "")

            if files_changed or new_files or diff_stat:
                checks.append({
                    "check": "code_changed_claim",
                    "status": "pass",
                    "detail": f"Evidence confirms changes: {len(files_changed)} modified, {len(new_files)} new files",
                })
            else:
                checks.append({
                    "check": "code_changed_claim",
                    "status": "warn",
                    "detail": "TeamResult claims code changes but no diff evidence found",
                })
                issues.append("TeamResult claims code changes but git diff is empty")
        else:
            checks.append({
                "check": "code_changed_claim",
                "status": "fail",
                "detail": "TeamResult claims code changes but no evidence file",
            })
            issues.append(f"TeamResult claims code changes but no evidence file for task '{task_id}'")
    else:
        checks.append({
            "check": "code_changed_claim",
            "status": "skip",
            "detail": "No 'code changed' claim in TeamResult",
        })

    # ── Check 4: "reviewed" claim ──
    _reviewed = any(kw in summary_lower for kw in ["reviewed", "code review", "review passed", "review complete", "peer review"])
    if _reviewed:
        evidence = _load_evidence(task_id, session)
        if evidence:
            after = evidence.get("after", {})
            files_changed = after.get("files_changed", [])
            if files_changed:
                checks.append({
                    "check": "reviewed_claim",
                    "status": "pass",
                    "detail": f"Evidence shows {len(files_changed)} files available for review",
                })
            else:
                checks.append({
                    "check": "reviewed_claim",
                    "status": "warn",
                    "detail": "TeamResult claims 'reviewed' but no files to review in evidence",
                })
        else:
            checks.append({
                "check": "reviewed_claim",
                "status": "warn",
                "detail": "TeamResult claims 'reviewed' but no evidence file",
            })
    else:
        checks.append({
            "check": "reviewed_claim",
            "status": "skip",
            "detail": "No 'reviewed' claim in TeamResult",
        })

    # ── Determine overall validity ──
    failed_checks = [c for c in checks if c["status"] == "fail"]
    valid = len(failed_checks) == 0

    result = {
        "valid": valid,
        "task_id": task_id,
        "loop_id": loop_id,
        "session": session or _session_id(),
        "validated_at": _now_iso(),
        "checks": checks,
        "issues": issues,
        "check_summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["status"] == "pass"),
            "fail": sum(1 for c in checks if c["status"] == "fail"),
            "warn": sum(1 for c in checks if c["status"] == "warn"),
            "skip": sum(1 for c in checks if c["status"] == "skip"),
        },
    }

    return result


def save_validation_result(result, session=None, session_id=""):
    """
    Save the TeamResult validation result.

    Args:
        result: dict — from validate_team_result()
        session: str — optional session ID (legacy)
        session_id: str — Phase 10.5: unified session ID

    Returns:
        str — path to validation file
    """
    session_dir = _session_dir(session_id or session)
    task_id = result.get("task_id", "unknown")
    path = os.path.join(session_dir, f"team-result-validation.json")

    # Load existing if any, merge
    existing = _load_json(path) or {"validations": []}
    if isinstance(existing, dict):
        existing.setdefault("validations", [])
        existing["validations"].append(result)
        existing["updated_at"] = _now_iso()
    else:
        existing = {"validations": [result], "updated_at": _now_iso()}

    with open(path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    return path


def get_validation_report(session=None):
    """
    Get the full validation report for a session.

    Returns:
        dict with all validation results
    """
    session_dir = _session_dir(session)
    path = os.path.join(session_dir, "team-result-validation.json")
    return _load_json(path) or {"validations": [], "updated_at": ""}


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 team_result_validator.py validate <team_result_file> [task_id] [session]")
        print("  python3 team_result_validator.py report [session]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "validate":
        tr_path = sys.argv[2] if len(sys.argv) > 2 else ""
        task_id = sys.argv[3] if len(sys.argv) > 3 else ""
        session = sys.argv[4] if len(sys.argv) > 4 else None

        if not tr_path or not os.path.exists(tr_path):
            print(f"Error: team result file not found: {tr_path}")
            sys.exit(1)

        import yaml
        with open(tr_path) as f:
            tr = yaml.safe_load(f)

        result = validate_team_result(tr, session=session, task_id=task_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        path = save_validation_result(result, session=session)
        print(f"\nValidation saved: {path}")

    elif cmd == "report":
        session = sys.argv[2] if len(sys.argv) > 2 else None
        report = get_validation_report(session)
        print(json.dumps(report, indent=2, ensure_ascii=False))