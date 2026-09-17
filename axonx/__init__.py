"""AxonX: asynchronous orchestration with isolated synchronous tasks."""

__version__ = "0.1.0"

from . import components, config, connectors, enums, plugin, schema, steps, task
from .components import registry as _component_registry
from .components.base import BaseComponent
from .components.client.base import BaseClient
from .components.job.base import BaseJob
from .components.machine.base import BaseMachineComponent
from .components.plugin.base import BasePluginComponent
from .components.proxy.base import BaseProxyComponent
from .components.service.base import BaseService
from .components.task_manager.base import BaseTaskManager
from .core import Application
from .steps.base import BaseStep
from .task.base import BaseInputParams, BaseOutputParams, BaseTask, TaskMetadata, TaskStep

_component_registry.R.freeze()

__all__ = [
    "Application",
    "BaseClient",
    "BaseComponent",
    "BaseInputParams",
    "BaseOutputParams",
    "TaskMetadata",
    "BaseJob",
    "BaseMachineComponent",
    "BasePluginComponent",
    "BaseProxyComponent",
    "BaseService",
    "BaseStep",
    "BaseTask",
    "BaseTaskManager",
    "TaskStep",
    "__version__",
    "components",
    "config",
    "connectors",
    "enums",
    "plugin",
    "schema",
    "steps",
    "task",
]
