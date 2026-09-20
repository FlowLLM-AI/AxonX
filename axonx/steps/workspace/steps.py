"""Thin Job adapters for workspace operations."""

import asyncio

from ...components.registry import provider
from ...workspace.browser import delete_workspace_entries, list_workspace_entries
from ...workspace.preview import PREVIEW_ROWS, preview_workspace_file
from ..base import BaseStep


@provider("workspace_list")
class ListEntriesStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            list_workspace_entries,
            self.workspace_path,
            self.context.get("path", ""),
        )


@provider("workspace_preview")
class PreviewFileStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            preview_workspace_file,
            self.workspace_path,
            self.context["path"],
            self.context.get("offset", 0),
            self.context.get("limit", PREVIEW_ROWS),
        )


@provider("workspace_delete")
class DeleteEntriesStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            delete_workspace_entries,
            self.workspace_path,
            self.context["paths"],
        )
