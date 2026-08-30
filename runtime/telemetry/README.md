# Runtime Telemetry

This directory stores operational event data for the Agent OS.

The system uses raw machine-readable event logs to evaluate:

- task execution quality
- route correctness
- skill effectiveness
- evolution impact

## Event categories

- `task-events.md`
- `routing-events.md`
- `skill-events.md`
- `evolution-events.md`
- `templates/event-template.yaml`

## Principle

Every meaningful task execution should produce at least one telemetry record so the system can be observed, evaluated, and improved.
