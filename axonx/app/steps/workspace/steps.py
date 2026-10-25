"""Thin Job adapters for workspace operations."""

import asyncio

from pydantic import TypeAdapter

from ..base import BaseStep
from ....common.registry import provider
from ....common.workspace.models import DeletedEntry, FilePreview, WorkspaceListing
from ....common.workspace.preview import PREVIEW_ROWS

FILE_PREVIEW = TypeAdapter(FilePreview)


@provider("workspace_list")
class ListEntriesStep(BaseStep):
    async def execute(self):
        listing = await asyncio.to_thread(
            self.workspace.list_entries,
            self.context.get("path", ""),
            offset=self.context.get("offset", 0),
        )
        self.response.answer = WorkspaceListing.model_validate(listing)


@provider("workspace_preview")
class PreviewFileStep(BaseStep):
    async def execute(self):
        preview = await asyncio.to_thread(
            self.workspace.preview_file,
            self.context["path"],
            self.context.get("offset", 0),
            self.context.get("limit", PREVIEW_ROWS),
            max_bytes=self.context.get("max_bytes"),
        )
        self.response.answer = FILE_PREVIEW.validate_python(preview)


@provider("workspace_delete")
class DeleteEntriesStep(BaseStep):
    async def execute(self):
        deleted = await asyncio.to_thread(
            self.workspace.delete_entries,
            self.context["paths"],
        )
        self.response.answer = [DeletedEntry.model_validate(entry) for entry in deleted]
