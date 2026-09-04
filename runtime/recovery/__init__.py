"""
Agent OS Recovery Layer — Phase 10: Autonomous Recovery Loop

Provides failure detection, recovery planning, and retry control
for the Agent OS runtime pipeline.

Modules:
  - failure_detector: Analyze audit evidence to detect failures
  - recovery_planner: Translate failures into recovery plans
  - retry_controller: Control limited retry execution (max 2)
  - recovery_integration: Wire recovery into loop_controller

All recovery actions are read-only regarding business code.
No auto-modification, no fake success, no auto-promotion.
"""