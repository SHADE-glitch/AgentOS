"""Agent OS engine.

A routing, memory and evolution layer that sits outside a coding agent:
it classifies a task, recalls relevant memory, hands context to the host
agent (which executes), then records the outcome and evolves memory.

Pure stdlib. Host integrations live in ``hosts/`` and are intentionally
out of scope for the engine package.
"""

__version__ = "0.1.0"
