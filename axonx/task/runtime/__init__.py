"""Synchronous execution and execution-owned services.

settings: Execution environment, workspace, timezone and advertised target settings.
process: Machine identity and exact process inspection, signalling and waits.
progress: Step execution, progress throttling and ordered event/metadata publication.
lifecycle: Startup checks, terminal outcomes, stale-record settlement and local termination.
replay: Deterministic business clocks and recorded-event delivery.
executor: Registered Task construction, execution, child calls, logs and resource cleanup.

Only execution settings load here. Import lifecycle services and the executor
from their owning modules.
"""

from . import settings

__all__ = [
    "settings",
]
