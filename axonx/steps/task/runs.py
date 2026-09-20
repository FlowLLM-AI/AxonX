"""Task-run workspace queries."""

import asyncio
from pathlib import Path

from ...components.registry import provider
from ...task.storage.workspace import METADATA_FILE
from ...workspace.browser import list_workspace_entries
from ...workspace.models import WorkspaceEntry
from ..base import BaseStep


def _is_task_run(path: Path, entry: WorkspaceEntry) -> bool:
    return entry.kind == "directory" and (path / METADATA_FILE).is_file()


@provider("task_runs")
class ListTaskRunsStep(BaseStep):
    """List task directories that contain a metadata document."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            list_workspace_entries,
            self.workspace_path,
            self.context["task_type"],
            include=_is_task_run,
        )
