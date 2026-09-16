"""Workspace browsing Job adapters."""

import asyncio

from ...components.registry import R
from ..base import BaseStep
from .listing import list_entries as _list_entries
from .paths import workspace_root
from .preview import CSV_PREVIEW_ROWS, preview_file as _preview_file


@R.register("list_workspace_entries_step")
class ListWorkspaceEntriesStep(BaseStep):
    """List one directory without walking the complete workspace tree."""

    async def execute(self):
        relative_path = self.context.get("path", "")
        self.response.answer = await asyncio.to_thread(
            _list_entries, workspace_root(self.app_config.workspace_dir), relative_path
        )


@R.register("preview_workspace_file_step")
class PreviewWorkspaceFileStep(BaseStep):
    """Return a bounded preview for one supported workspace file."""

    async def execute(self):
        relative_path = self.context["path"]
        offset = self.context.get("offset", 0)
        limit = min(self.context.get("limit", CSV_PREVIEW_ROWS), CSV_PREVIEW_ROWS)
        full = self.context.get("full", False)
        self.response.answer = await asyncio.to_thread(
            _preview_file,
            workspace_root(self.app_config.workspace_dir),
            relative_path,
            offset,
            limit,
            full,
        )
