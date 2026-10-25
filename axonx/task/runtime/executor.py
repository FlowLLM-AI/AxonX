"""Execute a named Task without knowing command-line or service protocols."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...common.constants import AXONX_DEFAULT_TIMEZONE
from ...common.workspace import Workspace
from ..catalog.resolver import resolve_task
from ..schemas.lifecycle import TaskMetadata
from .runner import TaskRunner


class TaskExecutor:
    def __init__(self, workspace_dir: str | Path, timezone: str = AXONX_DEFAULT_TIMEZONE):
        self.workspace = Workspace(workspace_dir)
        self.workspace_path = self.workspace.root
        self.timezone = timezone

    def execute(self, name: str, inputs: Mapping[str, Any] | None = None) -> TaskMetadata:
        if not isinstance(name, str) or not name:
            raise ValueError("Task name must be a non-empty string")
        task = resolve_task(name)(
            dict(inputs or {}), workspace_path=self.workspace_path, reg_name=name, timezone=self.timezone
        )
        return TaskRunner().run(task)
