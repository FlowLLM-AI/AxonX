"""Synchronous task base types and built-in tasks."""

from . import backtest, common, data, etl
from .backtest import RankingBacktestTask
from .base_task import BaseConfig, BaseTask, TaskStep
from .common import DemoTask
from .data import DownloadTushareTask
from .task_command_executor import TaskCatalog, TaskCommandExecutor, TaskExecution
from .task_runner import TaskRunner
from .task_resolver import installed_tasks, list_installed_task_infos, resolve_task
from .task_status_reporter import HttpTaskStatusReporter, TaskStatusReporter
from .task_status_manager import TaskStatusManager

__all__ = [
    "BaseConfig",
    "BaseTask",
    "TaskStep",
    "DemoTask",
    "DownloadTushareTask",
    "backtest",
    "common",
    "data",
    "etl",
    "HttpTaskStatusReporter",
    "TaskCatalog",
    "TaskCommandExecutor",
    "TaskExecution",
    "TaskRunner",
    "TaskStatusReporter",
    "TaskStatusManager",
    "RankingBacktestTask",
    "installed_tasks",
    "list_installed_task_infos",
    "resolve_task",
]
