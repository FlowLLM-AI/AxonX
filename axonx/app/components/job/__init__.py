"""Job contracts, invocation execution and response completion.

base: Shared Job contract, argument validation and invocation response handling.
command: Execute a service-owned CLI command with streaming output and cancellation cleanup.
pipeline: Ordered Steps with one task and bounded event queue per invocation.
"""

from . import base, command, pipeline

__all__ = [
    "base",
    "command",
    "pipeline",
]
