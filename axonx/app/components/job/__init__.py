"""Job contracts, invocation execution and response completion.

base: Shared Job contract, argument validation and invocation response handling.
command: Execute service-owned processes with streaming output and cancellation cleanup.
scheduled: Calendar-triggered pipeline Jobs.
pipeline: Ordered Steps with one task and bounded event queue per invocation.
"""

from . import base, command, pipeline, scheduled

__all__ = [
    "base",
    "command",
    "pipeline",
    "scheduled",
]
