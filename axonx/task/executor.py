"""Execute the Task-oriented ``exec`` command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..constants import AXONX_DEFAULT_TIMEZONE, CLI_RAW_ARGUMENTS
from ..schema import Command, TaskStatus
from .base import BaseTask
from .arguments import split_task_arguments
from .resolver import installed_tasks, resolve_task


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
        """Return the final process exit code."""
        return self.status.exit_code


class TaskCommandExecutor:
    """Turn one validated ``exec`` Command into a Task result."""

    def __init__(self, workspace_dir: str | Path, timezone: str = AXONX_DEFAULT_TIMEZONE) -> None:
        self.workspace_path = Path(workspace_dir).expanduser().resolve()
        self.timezone = timezone

    def execute(self, command: Command) -> TaskCatalog | TaskExecution:
        """Execute or enumerate tasks for one validated command."""
        if command.action != "exec":
            raise ValueError(f"Unsupported Task command: {command.action}")

        arguments = {key: value for key, value in command.arguments.items() if key != CLI_RAW_ARGUMENTS}
        if not arguments:
            return TaskCatalog(installed_tasks())

        name, config = split_task_arguments(arguments)
        task = resolve_task(name)(config, workspace_path=self.workspace_path, reg_name=name, timezone=self.timezone)
        output = task.execute()
        return TaskExecution(output, task.status)
