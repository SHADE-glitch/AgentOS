"""Guard tests for `run.sh` — the rig must not measure a project it can contaminate.

LGD-06-R2 was voided because the rig kept its tickets, logs, manifest and the captured
answer *inside* the measured project (`<cwd>/.arms/`). The agent listed the workspace,
read `.gitignore`, found `.arms/`, and `cat`-ed the previous attempt's diff before
writing its own. Nothing about Agent OS caused that; it was instrument placement, and
the fix is a refusal rather than a rule in somebody's head.

Every test here points `AOS_HOST_BIN` at `/bin/true`: a guard test that reached the host
would be spending a model call to prove a shell branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

LIVE = Path(__file__).resolve().parents[1]
RUN_SH = LIVE / "run.sh"
SCAFFOLD_MSG = "refusing: experiment scaffolding"
NESTED_MSG = "refusing: rig or store sits inside the measured project"


def run(cwd: Path, rig: Path) -> subprocess.CompletedProcess:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "AGENT_OS_ROOT": str(LIVE.parents[2]),
        "AOS_RIG": str(rig),
        "AOS_STORE_DIR": str(rig / "store"),
        "AOS_HOST_BIN": "/bin/true",
    }
    return subprocess.run(
        ["bash", str(RUN_SH), "guard-probe", str(cwd), "say nothing"],
        capture_output=True, text=True, env=env,
    )


def test_the_rig_refuses_a_scaffolding_directory_inside_the_project(tmp_path):
    project = tmp_path / "project"
    (project / ".arms" / "tickets").mkdir(parents=True)
    (project / ".arms" / "tickets" / "LGD-99.md").write_text("answer\n", encoding="utf-8")
    done = run(project, tmp_path / "rig")
    assert done.returncode != 0, "a project holding .arms/ must be refused before any model call"
    assert SCAFFOLD_MSG in done.stderr + done.stdout


def test_the_rig_refuses_a_rig_directory_inside_the_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    done = run(project, project / "rig")
    assert done.returncode != 0, "the rig lives where the subject can read it"
    assert NESTED_MSG in done.stderr + done.stdout


def test_a_clean_project_triggers_neither_placement_guard(tmp_path):
    """The guards refuse for placement, not for everything — otherwise the rig silently retires."""
    project = tmp_path / "project"
    project.mkdir()
    done = run(project, tmp_path / "rig")
    combined = done.stderr + done.stdout
    assert SCAFFOLD_MSG not in combined
    assert NESTED_MSG not in combined


def test_the_guards_run_before_any_host_call():
    text = RUN_SH.read_text(encoding="utf-8")
    host = text.find('"$host" run')
    assert host != -1, "run.sh no longer launches a host the way the rig expects"
    for message in (SCAFFOLD_MSG, NESTED_MSG):
        assert message in text, f"missing placement guard: {message}"
        assert text.find(message) < host, f"{message} must fire before the host is asked to work"
