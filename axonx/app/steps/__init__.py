"""Job adapters grouped by application capability.

base: Step execution, invocation state, component access and event emission.
agent: Agent turns, Task context and session-management operations.
common: General commands, help and version queries.
machine: Machine health, metrics, diagnostics and Python execution.
sync: Replica transfer, flush and synchronization-index operations.
task: Task catalogs, directories, status, lineage, logs and event streams.
update: Update requests, status queries and service restart.
workspace: Workspace listing, previews and deletion.
"""

from . import agent, base, common, machine, sync, task, update, workspace

__all__ = [
    "agent",
    "base",
    "common",
    "machine",
    "sync",
    "task",
    "update",
    "workspace",
]
