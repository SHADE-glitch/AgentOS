"""Multi-agent orchestration: rule-driven team formation and collaboration."""

from __future__ import annotations

from aos.core.orchestration.orchestrator import (
    TeamPlan,
    form_team,
    load_rules,
    reload,
    should_form_team,
)

__all__ = ["TeamPlan", "form_team", "load_rules", "reload", "should_form_team"]
