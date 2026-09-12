"""Execute the Task-oriented ``exec`` command."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..constants import CLI_RAW_ARGUMENTS
from ..schema import Command, TaskStatus
from .base_task import BaseTask
from .task_resolver import installed_tasks, resolve_task
from .task_runner import TaskRunner
from .task_status_reporter import create_task_status_reporter


@dataclass(frozen=True)
class TaskCatalog:
    """Collection returned when ``exec`` is called without a task."""

    tasks: dict[str, type[BaseTask]]


@dataclass(frozen=True)
class TaskExecution:
    """Completed task output together with its final status."""

    output: dict[str, Any]
    status: TaskStatus

    @property
    def exit_code(self) -> int:
        """Return the required process exit code from the final status."""
        if self.status.exit_code is None:
            raise RuntimeError("Task finished without an exit code")
        return self.status.exit_code


class TaskCommandExecutor:
    """Turn one validated ``exec`` Command into a Task result."""

    def execute(self, command: Command) -> TaskCatalog | TaskExecution:
        """Execute or enumerate tasks for one validated command."""
        if command.action != "exec":
            raise ValueError(f"Unsupported Task command: {command.action}")

        arguments = {key: value for key, value in command.arguments.items() if key != CLI_RAW_ARGUMENTS}
        if not arguments:
            return TaskCatalog(installed_tasks())

        name, config = self._task_arguments(arguments)
        task = resolve_task(name)(config)
        with create_task_status_reporter(task.logger) as reporter:
            status = TaskRunner(reporter.publish).run(task)
        return TaskExecution(task.output, status)

    @staticmethod
    def _task_arguments(arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Separate the task name from its validated configuration."""
        config = dict(arguments)
        try:
            name = config.pop("task")
        except KeyError:
            raise ValueError("Missing required option: --task") from None
        if not isinstance(name, str) or not name:
            raise ValueError("--task must be a non-empty string")
        return name, config
