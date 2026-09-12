"""AxonX: asynchronous orchestration with isolated synchronous tasks."""

__version__ = "0.1.0"

from .components import BaseComponent, R
from .components.job import BaseJob, JobMode, SimpleJob
from .components.task_manager import BaseTaskManager, LocalTaskManager
from .components import client
from .task import BaseTask, BaseConfig
from .steps import BaseStep
from .application import Application

R.freeze()

__all__ = [
    "Application",
    "BaseComponent",
    "BaseConfig",
    "BaseJob",
    "BaseStep",
    "BaseTask",
    "BaseTaskManager",
    "JobMode",
    "LocalTaskManager",
    "R",
    "SimpleJob",
    "__version__",
    "client",
]
