#!/usr/bin/env python3
"""
OpenCode Host Adapter — Phase 5.11

Minimal translation layer between OpenCode and Agent OS.

OpenCode
  ↓ (AGENTS.md instructions or CLI)
AOS Host Adapter
  ↓ (standardized task)
Agent OS Pipeline
  ↓ (result)
OpenCode Runtime

This adapter:
  1. Receives task from OpenCode (via CLI or environment)
  2. Translates to AOS format
  3. Invokes AOS loop controller
  4. Returns result to OpenCode

Constraints:
  - Does NOT duplicate Router, Memory, or Orchestrator
  - Does NOT hardcode models, agents, or providers
  - Only translates between host format and AOS format
"""

import sys
import os
import json
import subprocess
from datetime import datetime, timezone

# ── Constants ───────────────────────────────────────────────────
BASE = "/home/shade/.agents"
LOOP_CONTROLLER = os.path.join(BASE, "runtime", "loop-controller", "loop_controller.py")
RUNTIME_ADAPTER = os.path.join(BASE, "runtime", "loop-controller", "runtime_adapter.py")

# Resolved from environment, never hardcoded
DEFAULT_PROVIDER = os.environ.get("AOS_RUNTIME_PROVIDER", "opencode")
DEFAULT_MODEL = os.environ.get("AOS_RUNTIME_MODEL", "")


def resolve_task_from_opencode():
    """
    Resolve task from OpenCode environment.
    
    OpenCode provides:
      - AOS_TASK: task description (from AGENTS.md instruction)
      - AOS_MEMORY: memory mode (default: enabled)
      - AOS_MODEL: model override (optional)
      - AOS_PROVIDER: provider override (optional)
      - PWD / OLDPWD: working directory context
    """
    task = os.environ.get("AOS_TASK", "")
    memory_mode = os.environ.get("AOS_MEMORY", "enabled")
    model = os.environ.get("AOS_MODEL", DEFAULT_MODEL)
    provider = os.environ.get("AOS_PROVIDER", DEFAULT_PROVIDER)
    cwd = os.environ.get("PWD", os.getcwd())

    return {
        "task": task,
        "memory_mode": memory_mode,
        "model": model,
        "provider": provider,
        "working_directory": cwd,
    }


def resolve_task_from_cli(args):
    """
    Resolve task from CLI arguments.
    
    Usage: python3 opencode_adapter.py "task description" [--memory on|off] [--model MODEL] [--provider PROVIDER]
    """
    if len(args) < 1:
        return None

    task = args[0]
    memory_mode = "enabled"
    model = DEFAULT_MODEL
    provider = DEFAULT_PROVIDER
    cwd = os.getcwd()

    i = 1
    while i < len(args):
        if args[i] == "--memory" and i + 1 < len(args):
            memory_mode = "enabled" if args[i + 1] == "on" else "disabled"
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
            i += 2
        elif args[i] == "--cwd" and i + 1 < len(args):
            cwd = args[i + 1]
            i += 2
        else:
            i += 1

    return {
        "task": task,
        "memory_mode": memory_mode,
        "model": model,
        "provider": provider,
        "working_directory": cwd,
    }


def invoke_aos(task_spec):
    """
    Invoke the AOS loop controller with the resolved task.
    
    Returns: dict with AOS result
    """
    import uuid

    task_id = f"HOST-{uuid.uuid4().hex[:6].upper()}"
    task_text = task_spec["task"]
    memory_mode = task_spec["memory_mode"]
    model = task_spec["model"]
    provider = task_spec["provider"]
    cwd = task_spec["working_directory"]

    # Build entry metadata for AOS
    entry_metadata = {
        "entry_type": "host_adapter",
        "adapter": "opencode",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "cwd": cwd,
        "task_id": task_id,
    }

    # Build loop_controller command
    cmd = [
        sys.executable,
        LOOP_CONTROLLER,
        task_id,
        task_text,
        memory_mode,
        model,
        provider,
    ]

    print(f"[opencode-adapter] task_id={task_id}")
    print(f"[opencode-adapter] provider={provider}")
    print(f"[opencode-adapter] model={model}")
    print(f"[opencode-adapter] cwd={cwd}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env={
                **os.environ,
                "AGENT_OS_ROOT": BASE,
                "AOS_ENTRY_METADATA": json.dumps(entry_metadata),
            },
            capture_output=True,
            text=True,
            timeout=600,
        )

        return {
            "status": "success" if result.returncode == 0 else "error",
            "task_id": task_id,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "task_id": task_id,
            "exit_code": -1,
            "stdout": "",
            "stderr": "AOS pipeline timed out after 600s",
        }
    except Exception as e:
        return {
            "status": "error",
            "task_id": task_id,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
        }


def main():
    """CLI entry point."""
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("OpenCode Host Adapter — Phase 5.11")
        print()
        print("Usage:")
        print('  python3 opencode_adapter.py "task description" [options]')
        print()
        print("Options:")
        print("  --memory on|off     Memory retrieval mode (default: on)")
        print("  --model MODEL       Model override (default: AOS_RUNTIME_MODEL env)")
        print("  --provider PROVIDER Provider override (default: opencode)")
        print("  --cwd DIR           Working directory (default: current)")
        print()
        print("Environment variables:")
        print("  AOS_TASK            Task description")
        print("  AOS_MEMORY          Memory mode")
        print("  AOS_MODEL           Model override")
        print("  AOS_PROVIDER        Provider override")
        sys.exit(0)

    # Resolve task from CLI
    task_spec = resolve_task_from_cli(sys.argv[1:])
    if not task_spec or not task_spec["task"]:
        print("Error: no task specified", file=sys.stderr)
        sys.exit(1)

    # Invoke AOS
    result = invoke_aos(task_spec)

    # Output result
    print(f"\n[adapter] status={result['status']}")
    print(f"[adapter] task_id={result['task_id']}")

    if result["status"] != "success":
        print(f"[adapter] error={result['stderr'][:200]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
