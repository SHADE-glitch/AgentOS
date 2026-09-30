#!/usr/bin/env python3
"""
Host Integration Trace — Phase 6.0.4

Provides traceability for Host Integration events.
This is SEPARATE from Runtime Execution traces.

Evidence Types:
  - host_integration: Events from Host Plugin → AOS Adapter → Router/Memory/Orchestrator
  - runtime_execution: Events from AOS → Runtime Adapter → Agent/Model

This module only handles host_integration traces.

Pipeline:
  OpenCode Plugin
    ↓ (calls adapter)
  AOS Host Adapter
    ↓ (calls this module)
  Host Trace
    ↓ (writes to telemetry)
  /home/shade/.agents/runtime/telemetry/host-events.yaml
"""

import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────
BASE = "/home/shade/.agents"
TELEMETRY_DIR = os.path.join(BASE, "runtime", "telemetry")
HOST_EVENTS_FILE = os.path.join(TELEMETRY_DIR, "host-events.yaml")
HOST_TRACE_DIR = os.path.join(BASE, "runtime", "traces", "host")

# Ensure directories exist
os.makedirs(TELEMETRY_DIR, exist_ok=True)
os.makedirs(HOST_TRACE_DIR, exist_ok=True)


# ── Event Types ──────────────────────────────────────────────────
class HostEventType:
    PLUGIN_LOADED = "host_plugin_loaded"
    PLUGIN_UNLOADED = "host_plugin_unloaded"
    PROMPT_RECEIVED = "host_prompt_received"
    ADAPTER_CALLED = "host_adapter_called"
    ADAPTER_COMPLETED = "host_adapter_completed"
    ROUTING_COMPLETED = "host_routing_completed"
    MEMORY_RETRIEVED = "host_memory_retrieved"
    ORCHESTRATION_COMPLETED = "host_orchestration_completed"
    CONTEXT_INJECTED = "host_context_injected"
    RECURSION_DETECTED = "host_recursion_detected"
    FALLBACK_TRIGGERED = "host_fallback_triggered"
    ERROR_OCCURRED = "host_error_occurred"


# ── Trace Record ─────────────────────────────────────────────────
class HostTrace:
    """Manages host integration traces."""
    
    def __init__(self, session_id: str = "", working_directory: str = ""):
        self.session_id = session_id or f"HOST-SES-{uuid.uuid4().hex[:8].upper()}"
        self.working_directory = working_directory or os.getcwd()
        self.trace_id = f"HOST-TRACE-{uuid.uuid4().hex[:8].upper()}"
        self.start_time = datetime.now(timezone.utc)
        self.events = []
        self.trace_file = os.path.join(HOST_TRACE_DIR, f"{self.trace_id}.yaml")
        
    def emit(self, event_type: str, **kwargs):
        """Emit a host integration event."""
        event = {
            "event_id": f"EVT-{uuid.uuid4().hex[:8].upper()}",
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "working_directory": self.working_directory,
            "evidence_type": "host_integration",
            **kwargs
        }
        self.events.append(event)
        return event
    
    def save(self):
        """Save trace to file."""
        trace_data = {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "working_directory": self.working_directory,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "event_count": len(self.events),
            "events": self.events
        }
        
        # Write YAML manually (no PyYAML dependency)
        yaml_content = self._to_yaml(trace_data)
        Path(self.trace_file).write_text(yaml_content)
        
        # Also update host-events.yaml
        self._update_host_events()
        
        return self.trace_file
    
    def _to_yaml(self, data, indent=0):
        """Simple YAML serializer."""
        lines = []
        prefix = "  " * indent
        
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.append(self._to_yaml(value, indent + 1))
                elif isinstance(value, str):
                    lines.append(f'{prefix}{key}: "{value}"')
                elif isinstance(value, bool):
                    lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
                elif isinstance(value, (int, float)):
                    lines.append(f"{prefix}{key}: {value}")
                elif value is None:
                    lines.append(f"{prefix}{key}: null")
                else:
                    lines.append(f'{prefix}{key}: "{value}"')
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    lines.append(self._to_yaml(item, indent + 1))
                else:
                    lines.append(f'{prefix}- "{item}"')
        
        return "\n".join(lines)
    
    def _update_host_events(self):
        """Update the aggregated host-events.yaml file."""
        events_data = []
        
        # Read existing events if file exists
        if os.path.exists(HOST_EVENTS_FILE):
            try:
                content = Path(HOST_EVENTS_FILE).read_text()
                # Simple parsing - just append new events
                # In production, use proper YAML parser
            except:
                pass
        
        # Append new events
        for event in self.events:
            events_data.append(event)
        
        # Write aggregated events
        yaml_lines = [
            "# Host Integration Telemetry Log",
            "# Phase 6.0.4 — All host integration events",
            "# Auto-generated from host plugin. Do not manually edit.",
            "",
            'version: "1.0"',
            'phase: "6.0.4"',
            f'last_updated: "{datetime.now(timezone.utc).isoformat()}"',
            "",
            "# ============================================================",
            "# Host Integration Events",
            "# ============================================================",
            "",
            "events:",
        ]
        
        for event in self.events:
            yaml_lines.append(f"  - event_id: \"{event['event_id']}\"")
            yaml_lines.append(f"    event_type: \"{event['event_type']}\"")
            yaml_lines.append(f"    timestamp: \"{event['timestamp']}\"")
            yaml_lines.append(f"    trace_id: \"{event['trace_id']}\"")
            yaml_lines.append(f"    session_id: \"{event['session_id']}\"")
            yaml_lines.append(f"    evidence_type: \"{event['evidence_type']}\"")
            for key, value in event.items():
                if key not in ['event_id', 'event_type', 'timestamp', 'trace_id', 'session_id', 'evidence_type']:
                    if isinstance(value, str):
                        yaml_lines.append(f"    {key}: \"{value}\"")
                    elif isinstance(value, (int, float)):
                        yaml_lines.append(f"    {key}: {value}")
                    elif isinstance(value, bool):
                        yaml_lines.append(f"    {key}: {'true' if value else 'false'}")
                    elif isinstance(value, list):
                        yaml_lines.append(f"    {key}:")
                        for item in value:
                            yaml_lines.append(f"      - \"{item}\"")
            yaml_lines.append("")
        
        Path(HOST_EVENTS_FILE).write_text("\n".join(yaml_lines))


# ── Convenience Functions ────────────────────────────────────────
def emit_plugin_loaded(session_id: str = "", working_directory: str = ""):
    """Emit plugin loaded event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.PLUGIN_LOADED,
        plugin_name="opencode-aos-host",
        plugin_version="0.1.0",
        pid=os.getpid(),
        cwd=working_directory or os.getcwd()
    )
    trace.save()
    return event


def emit_prompt_received(prompt: str, session_id: str = "", working_directory: str = ""):
    """Emit prompt received event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.PROMPT_RECEIVED,
        prompt_summary=prompt[:200],
        prompt_length=len(prompt)
    )
    trace.save()
    return event


def emit_adapter_called(task_id: str, prompt: str, session_id: str = "", working_directory: str = ""):
    """Emit adapter called event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.ADAPTER_CALLED,
        task_id=task_id,
        prompt_summary=prompt[:200]
    )
    trace.save()
    return event


def emit_adapter_completed(task_id: str, aos_status: str, lead_agent: str, memory_count: int, session_id: str = "", working_directory: str = ""):
    """Emit adapter completed event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.ADAPTER_COMPLETED,
        task_id=task_id,
        aos_status=aos_status,
        lead_agent=lead_agent,
        memory_count=memory_count
    )
    trace.save()
    return event


def emit_context_injected(task_id: str, injection_status: str, session_id: str = "", working_directory: str = ""):
    """Emit context injected event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.CONTEXT_INJECTED,
        task_id=task_id,
        injection_status=injection_status
    )
    trace.save()
    return event


def emit_recursion_detected(session_id: str = "", working_directory: str = ""):
    """Emit recursion detected event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.RECURSION_DETECTED,
        status="skipped",
        reason="recursion_detected"
    )
    trace.save()
    return event


def emit_fallback_triggered(task_id: str, reason: str, session_id: str = "", working_directory: str = ""):
    """Emit fallback triggered event."""
    trace = HostTrace(session_id, working_directory)
    event = trace.emit(
        HostEventType.FALLBACK_TRIGGERED,
        task_id=task_id,
        fallback_reason=reason
    )
    trace.save()
    return event


# ── CLI Interface ────────────────────────────────────────────────
def main():
    """CLI entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Host Integration Trace")
    parser.add_argument("event_type", help="Event type to emit")
    parser.add_argument("--session", default="", help="Session ID")
    parser.add_argument("--cwd", default="", help="Working directory")
    parser.add_argument("--task-id", default="", help="Task ID")
    parser.add_argument("--prompt", default="", help="Prompt text")
    parser.add_argument("--status", default="", help="Status")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if args.event_type == "plugin_loaded":
        event = emit_plugin_loaded(args.session, args.cwd)
    elif args.event_type == "prompt_received":
        event = emit_prompt_received(args.prompt, args.session, args.cwd)
    elif args.event_type == "adapter_called":
        event = emit_adapter_called(args.task_id, args.prompt, args.session, args.cwd)
    elif args.event_type == "adapter_completed":
        event = emit_adapter_completed(args.task_id, args.status, "general", 0, args.session, args.cwd)
    elif args.event_type == "context_injected":
        event = emit_context_injected(args.task_id, args.status, args.session, args.cwd)
    elif args.event_type == "recursion_detected":
        event = emit_recursion_detected(args.session, args.cwd)
    elif args.event_type == "fallback_triggered":
        event = emit_fallback_triggered(args.task_id, args.status, args.session, args.cwd)
    else:
        print(f"Unknown event type: {args.event_type}", file=sys.stderr)
        sys.exit(1)
    
    if args.json:
        print(json.dumps(event, indent=2, ensure_ascii=False))
    else:
        print(f"Event emitted: {event['event_id']}")
        print(f"Event type: {event['event_type']}")
        print(f"Trace ID: {event['trace_id']}")


if __name__ == "__main__":
    import sys
    main()
