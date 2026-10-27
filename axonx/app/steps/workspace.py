"""Thin Job adapters for workspace operations."""

import asyncio

from ..components.registry import provider
from ..workspace.preview import PREVIEW_ROWS
from .base import BaseStep


@provider("workspace_list")
class ListEntriesStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            self.workspace.list_entries,
            self.context.get("path", ""),
            offset=self.context.get("offset", 0),
        )


@provider("workspace_preview")
class PreviewFileStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            self.workspace.preview_file,
            self.context["path"],
            self.context.get("offset", 0),
            self.context.get("limit", PREVIEW_ROWS),
            max_bytes=self.context.get("max_bytes"),
        )


@provider("workspace_delete")
class DeleteEntriesStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            self.workspace.delete_entries,
            self.context["paths"],
        )
