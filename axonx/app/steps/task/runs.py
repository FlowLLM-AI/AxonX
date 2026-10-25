"""Task-run workspace queries."""

import asyncio
from pathlib import Path

from ....common.registry import provider
from ....common.workspace.models import WorkspaceListing
from ....task.storage.workspace import METADATA_FILE
from ..base import BaseStep


def _is_task_run(path: Path, entry: dict) -> bool:
    return entry["kind"] == "directory" and (path / METADATA_FILE).is_file()


@provider("task_runs")
class ListTaskRunsStep(BaseStep):
    """List task directories that contain a metadata document."""

    async def execute(self):
        listing = await asyncio.to_thread(
            self.workspace.list_entries,
            self.context["task_type"],
            include=_is_task_run,
        )
        self.response.answer = WorkspaceListing.model_validate(listing)
