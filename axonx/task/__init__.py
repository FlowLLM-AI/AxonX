"""Synchronous task base types and dependency-free built-in tasks."""

from .base_task import BaseConfig, BaseTask

from .common import DemoTask
from .task_command_executor import TaskCatalog, TaskCommandExecutor, TaskExecution
from .task_runner import TaskRunner
from .task_resolver import installed_tasks, resolve_task
from .task_status_reporter import HttpTaskStatusReporter, TaskStatusReporter
from .task_status_manager import TaskStatusManager

__all__ = [
    "BaseConfig",
    "BaseTask",
    "DemoTask",
    "HttpTaskStatusReporter",
    "TaskCatalog",
    "TaskCommandExecutor",
    "TaskExecution",
    "TaskRunner",
    "TaskStatusReporter",
    "TaskStatusManager",
    "installed_tasks",
    "resolve_task",
]
