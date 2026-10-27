"""Job adapters grouped into one module per application capability.

agent: Agent turn and session-management Steps.
base: Base type for asynchronous job steps.
common: General-purpose application Steps.
machine: Job adapters for machine status, health, diagnostics and Python execution.
sync: Job adapters for configured synchronization components.
task: Read-only Task query Steps.
update: Application self-update Job Steps.
workspace: Workspace Job Steps.
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
