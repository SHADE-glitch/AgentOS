#!/usr/bin/env python3
"""
AOS Bootstrap for Freebuff — Phase 7.1

Calls the existing AOS Host Adapter and formats the decision context
for injection into Freebuff's prompt pipeline.

This is the Python backend called by the UserPromptSubmit hook.

Pipeline:
  Freebuff UserPromptSubmit hook (prompt_submit.sh)
    ↓ (calls this script with task text)
  AOS Bootstrap (this file)
    ↓ (calls aos_host_adapter.py)
  Router / Memory / Orchestrator
    ↓ (returns decision context)
  AOS Bootstrap
    ↓ (formats as prompt prefix)
  Hook script
    ↓ (outputs modified prompt)
  Freebuff (continues with AOS context)

CRITICAL CONSTRAINTS:
  - Does NOT call runtime_adapter (would cause recursion)
  - Does NOT start new agent instances
  - Only CALLS existing components and returns context
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

# ── Path Setup ────────────────────────────────────────────────────
AOS_ROOT = os.environ.get("AGENT_OS_ROOT", os.path.expanduser("~/.agents"))
ADAPTER_PATH = os.path.join(AOS_ROOT, "runtime", "hosts", "opencode", "aos_host_adapter.py")

# ── Recursion Guard ───────────────────────────────────────────────
RECURSION_ENV = "AOS_HOST_PLUGIN_ACTIVE"

def check_recursion():
    if os.environ.get(RECURSION_ENV):
        return True
    os.environ[RECURSION_ENV] = "1"
    return False

def clear_recursion():
    os.environ.pop(RECURSION_ENV, None)


# ── Call AOS Adapter ─────────────────────────────────────────────
def call_aos_adapter(task_text, working_directory="", session_id=""):
    """
    Call the existing AOS Host Adapter via subprocess.
    Returns the decision context dict.
    """
    import subprocess

    task_id = f"FREEBUFF-{uuid.uuid4().hex[:6].upper()}"

    cmd = [
        sys.executable,
        ADAPTER_PATH,
        task_text,
        "--json",
        "--task-id", task_id,
    ]

    if working_directory:
        cmd.extend(["--cwd", working_directory])
    if session_id:
        cmd.extend(["--session", session_id])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,  # 15s timeout for bootstrap
            env={
                **os.environ,
                RECURSION_ENV: "1",
            },
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout.strip())

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        return None
    finally:
        clear_recursion()


# ── Format Context as Prompt Prefix ──────────────────────────────
def format_context_prefix(context):
    """
    Format AOS decision context as a prompt prefix string.
    This gets prepended to the user's prompt.
    """
    if not context or context.get("aos_status") in ("fallback", "unavailable", None):
        return ""

    lines = []

    # Header
    lines.append("[Agent OS Context — auto-injected]")
    lines.append("")

    # Task classification
    cls = context.get("decision", {}).get("classification", {})
    if cls:
        category = cls.get("category", "")
        difficulty = cls.get("difficulty", "")
        roles = cls.get("roles", [])

        parts = []
        if category:
            parts.append(f"Category: {category}")
        if difficulty:
            parts.append(f"Difficulty: {difficulty}")
        if roles:
            parts.append(f"Recommended role: {roles[0]}")
        if parts:
            lines.append(" | ".join(parts))

    # Orchestration
    lead = context.get("orchestration", {}).get("lead_agent", "")
    if lead and lead != "general":
        lines.append(f"Lead agent role: {lead}")

    # Memory
    mem_count = context.get("memory", {}).get("retrieved", 0)
    if mem_count > 0:
        memories = context.get("memory", {}).get("memories", [])
        lines.append(f"Relevant memories: {mem_count}")
        for mem in memories[:3]:
            mid = mem.get("memory_id", "?")
            content = mem.get("content", "")
            if content:
                lines.append(f"  - {mid}: {content[:120]}")
            else:
                lines.append(f"  - {mid}")

    # Warnings
    warnings = context.get("warnings", [])
    if warnings:
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ⚠ {w}")

    # Instructions
    instructions = context.get("instructions", [])
    if instructions:
        lines.append("AOS recommendations:")
        for i in instructions:
            lines.append(f"  → {i}")

    lines.append("")
    lines.append("[Use this context to inform your approach. AOS provides decision support, not execution.]")
    lines.append("")

    return "\n".join(lines)


# ── Main Entry Point ─────────────────────────────────────────────
def main():
    """
    Read task from stdin (JSON format) and output the AOS context prefix.
    
    Input (stdin): {"task": "...", "cwd": "...", "session_id": "..."}
    Output (stdout): The prompt prefix to inject (empty string if AOS unavailable)
    """
    if check_recursion():
        # Recursion detected, output nothing (pass-through)
        print("", end="")
        return

    try:
        # Read input
        input_data = sys.stdin.read().strip()
        if not input_data:
            print("", end="")
            return

        request = json.loads(input_data)
        task = request.get("task", "")
        cwd = request.get("cwd", "")
        session_id = request.get("session_id", "")

        if not task:
            print("", end="")
            return

        # Call AOS adapter
        context = call_aos_adapter(task, working_directory=cwd, session_id=session_id)

        # Format and output
        prefix = format_context_prefix(context)
        print(prefix, end="")

    except Exception:
        # On any error, output nothing (graceful degradation)
        print("", end="")
    finally:
        clear_recursion()


if __name__ == "__main__":
    main()
