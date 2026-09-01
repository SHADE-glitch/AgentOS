"""
Orchestrator Runtime — Phase 7.3

Minimal team formation from Router DecisionContext.
Implements R1-R10 team selection rules and C1-C2 conflict rules.
"""

try:
    from .team import TeamPlan, load_role_registry
    from .orchestrator import Orchestrator, form_team
except ImportError:
    from team import TeamPlan, load_role_registry
    from orchestrator import Orchestrator, form_team

__all__ = ["TeamPlan", "Orchestrator", "form_team", "load_role_registry"]
