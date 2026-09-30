"""Agent OS engine.

A routing, memory and evolution layer that sits outside a coding agent:
it classifies a task, recalls relevant memory, hands context to the host
agent (which executes), then records the outcome and evolves memory.

Pure stdlib. A host reaches the engine through ``bin/aos`` and the JSON
contract in ``aos/contract/``; host-side integration code is a separate
artifact and is deliberately not part of this package.
"""

__version__ = "0.1.0"
