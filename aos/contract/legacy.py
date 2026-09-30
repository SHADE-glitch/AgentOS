"""Render the frozen preflight contract into the legacy nested shape.

The old ``aos_host_adapter.get_decision_context`` returned a nested
document (``decision.classification`` / ``orchestration.lead_agent`` ...).
New code should consume the flat contract directly; this module exists only
so a consumer still on the old shape keeps working.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_LEGACY_STATUS = {"ok": "completed", "degraded": "completed", "fallback": "fallback"}


def to_adapter_context(preflight: dict[str, Any]) -> dict[str, Any]:
    """Convert a preflight document into the legacy nested adapter context."""
    router = preflight.get("router", {})
    lead_agent = router.get("lead_role") or "general"
    support_agents = list(router.get("support_roles", []))

    return {
        "task_id": preflight.get("task_id", ""),
        "task_text": preflight.get("task_text", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": preflight.get("session_id", ""),
        "working_directory": preflight.get("artifacts", {}).get("cwd", ""),
        "runtime": {
            "provider": preflight.get("artifacts", {}).get("provider", ""),
            "model": preflight.get("artifacts", {}).get("model", ""),
        },
        "aos_status": _LEGACY_STATUS.get(preflight.get("aos_status", ""), "fallback"),
        "decision": {"classification": dict(preflight.get("classification", {}))},
        "memory": dict(preflight.get("memory", {})),
        "orchestration": {"lead_agent": lead_agent, "support_agents": support_agents},
        "warnings": list(preflight.get("warnings", [])),
        "instructions": [],
    }
