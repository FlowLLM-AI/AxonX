"""Task directory workspace queries."""

import asyncio
from pathlib import Path

from ...registry import provider
from ...workspace.models import WorkspaceEntry
from ..base import BaseStep


def _is_task_directory(path: Path, entry: WorkspaceEntry) -> bool:
    return entry.kind == "directory" and (path / "metadata.json").is_file()


@provider("task_directories")
class ListTaskDirectoriesStep(BaseStep):
    """List task directories that contain a metadata document."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            self.workspace.list_entries,
            self.context["task_type"],
            include=_is_task_directory,
        )
