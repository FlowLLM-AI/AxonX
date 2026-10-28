"""Component domains and shared component contracts.

agent: Agent backends and their shared session and event contracts.
base: Shared component context, dependency declarations, and managed lifecycle.
cron: Application-owned scheduling of daemon-owned commands.
job: Job execution, response contracts and Step pipelines.
machine: Managed machine observation, diagnostics and Python execution.
proxy: Proxy contracts and built-in forwarding implementations.
registry: Explicit provider declarations and application-local provider lookup.
service: Remotely callable service contracts and implementations.
sync: Task display-replica planning, transfer and application.
task_index: Task observation: indexing, lineage, summaries and event streams.
updater: Application update admission and status.
"""

from . import agent, base, cron, job, machine, proxy, registry, service, sync, task_index, updater

__all__ = [
    "agent",
    "base",
    "cron",
    "job",
    "machine",
    "proxy",
    "registry",
    "service",
    "sync",
    "task_index",
    "updater",
]
