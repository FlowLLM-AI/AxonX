"""Execute registered Tasks through a caller-supplied resolver."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..core.task import BaseTask
from ..models.lifecycle import TaskMetadata
from .runner import TaskRunner


class TaskExecutor:
    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        resolve_task: Callable[[str], type[BaseTask]],
        timezone: str = "Asia/Shanghai",
        execution_target: str | None = None,
    ) -> None:
        self.workspace_path = Path(workspace_dir).expanduser().resolve()
        self.resolve_task = resolve_task
        self.timezone = timezone
        self.execution_target = execution_target

    def execute(self, name: str, inputs: Mapping[str, Any] | None = None) -> TaskMetadata:
        if not isinstance(name, str) or not name:
            raise ValueError("Task name must be a non-empty string")
        task = self.resolve_task(name)(
            dict(inputs or {}),
            workspace_path=self.workspace_path,
            reg_name=name,
            timezone=self.timezone,
            execution_target=self.execution_target,
        )
        return TaskRunner(resolve_task=self.resolve_task).run(task)
