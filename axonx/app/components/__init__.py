"""Component domains and shared component contracts.

base: Component identity, application access, dependency injection and lifecycle.
component_type: Built-in component domain names.
agent: Agent backends, message events, sessions and transcript storage.
cron: Application scheduling of daemon-owned commands.
job: Job contracts, invocation context, response events and Step pipelines.
proxy: Reverse-proxy contracts and HTTP forwarding.
service: Remotely callable services and HTTP endpoints.
sync: Bounded display-replica planning, transfer and archive application.
task_index: Task observation, summaries, lineage and event streams.
updater: Application update admission and response-completion handoff.

Import component contracts and implementations from their owning modules.
"""

from . import component_type
from .component_type import ComponentType

__all__ = [
    "ComponentType",
    "component_type",
]
