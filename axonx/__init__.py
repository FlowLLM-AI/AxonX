"""AxonX public API, loaded only when a capability is requested."""

from importlib import import_module
from ._version import VERSION as __version__

_EXPORTS = {
    "Application": ("app.core", "Application"),
    "BaseAgentComponent": ("app.components.agent.base", "BaseAgentComponent"),
    "BaseClient": ("app.components.client", "BaseClient"),
    "BaseComponent": ("app.components.base", "BaseComponent"),
    "BaseJob": ("app.components.job.base", "BaseJob"),
    "BaseProxyComponent": ("app.components.proxy.base", "BaseProxyComponent"),
    "BaseService": ("app.components.service.base", "BaseService"),
    "BaseStep": ("app.steps.base", "BaseStep"),
    "BaseSyncComponent": ("app.components.sync.base", "BaseSyncComponent"),
    "BaseTaskRepository": ("app.components.task_repository.base", "BaseTaskRepository"),
    "PipelineJob": ("app.components.job.pipeline", "PipelineJob"),
    "provider": ("plugin.registry", "provider"),
    "BaseTask": ("task.core", "BaseTask"),
    "BaseInputParams": ("task.core", "BaseInputParams"),
    "BaseOutputParams": ("task.core", "BaseOutputParams"),
    "TaskStep": ("task.core", "TaskStep"),
    "TaskMetadata": ("task.schemas.lifecycle", "TaskMetadata"),
}
__all__ = [*_EXPORTS, "__version__"]


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, symbol = _EXPORTS[name]
    value = getattr(import_module(f".{module}", __name__), symbol)
    globals()[name] = value
    return value
