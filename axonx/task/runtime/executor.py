"""Execute the Task-oriented ``exec`` command."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ...constants import (
    AXONX_DEFAULT_TIMEZONE,
    AXONX_TASK_CREATED_AT,
    AXONX_TASK_ID,
    AXONX_TASK_RUN_ID,
    CLI_EXEC_COMMAND,
    CLI_RAW_ARGUMENTS,
)
from ..catalog.resolver import installed_tasks, resolve_task
from ..core.task import BaseTask
from ..storage.workspace import TaskStatus
from .arguments import split_task_arguments
from .runner import TaskRunner

if TYPE_CHECKING:
    from ...cli.parser import Command


@dataclass(frozen=True)
class TaskCatalog:
    """Collection returned when ``exec`` is called without a task."""

    tasks: dict[str, type[BaseTask]]


@dataclass(frozen=True)
class TaskExecution:
    """Completed task output together with its final status."""

    output: dict
    status: TaskStatus

    @property
    def exit_code(self) -> int:
        """Return the final process exit code."""
        return self.status.exit_code


class TaskCommandExecutor:
    """Turn one validated ``exec`` Command into a Task result."""

    def __init__(
        self, workspace_dir: str | Path, timezone: str = AXONX_DEFAULT_TIMEZONE
    ) -> None:
        self.workspace_path = Path(workspace_dir).expanduser().resolve()
        self.timezone = timezone

    def execute(self, command: Command) -> TaskCatalog | TaskExecution:
        """Execute or enumerate tasks for one validated command."""
        if command.action != CLI_EXEC_COMMAND:
            raise ValueError(f"Unsupported Task command: {command.action}")

        arguments = {
            key: value
            for key, value in command.arguments.items()
            if key != CLI_RAW_ARGUMENTS
        }
        if not arguments:
            return TaskCatalog(installed_tasks())

        name, config = split_task_arguments(arguments)
        created_at = os.environ.get(AXONX_TASK_CREATED_AT)
        task = resolve_task(name)(
            config,
            workspace_path=self.workspace_path,
            reg_name=name,
            timezone=self.timezone,
            task_id=os.environ.get(AXONX_TASK_ID),
            run_id=os.environ.get(AXONX_TASK_RUN_ID),
            created_at=datetime.fromisoformat(created_at) if created_at else None,
        )
        status = TaskRunner().run(task)
        return TaskExecution(task.output, status)
