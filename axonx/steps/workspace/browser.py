"""Workspace browsing and deletion Job adapters."""

import asyncio

from ...components.registry import R
from ..base import BaseStep
from .files import delete_entries as _delete_entries, delete_entry as _delete_entry, list_entries as _list_entries
from .paths import workspace_root
from .preview import CSV_MAX_ROWS, CSV_PREVIEW_ROWS, preview_file as _preview_file


@R.register("list_workspace_entries_step")
class ListWorkspaceEntriesStep(BaseStep):
    """List one directory without walking the complete workspace tree."""

    async def execute(self):
        relative_path = self.context.get("path", "")
        require_metadata = self.context.get("require_metadata", False)
        self.response.answer = await asyncio.to_thread(
            _list_entries, workspace_root(self.app_config.workspace_dir), relative_path, require_metadata
        )


@R.register("preview_workspace_file_step")
class PreviewWorkspaceFileStep(BaseStep):
    """Return a bounded preview for one supported workspace file."""

    async def execute(self):
        relative_path = self.context["path"]
        offset = self.context.get("offset", 0)
        limit = min(self.context.get("limit", CSV_PREVIEW_ROWS), CSV_MAX_ROWS)
        full = self.context.get("full", False)
        self.response.answer = await asyncio.to_thread(
            _preview_file,
            workspace_root(self.app_config.workspace_dir),
            relative_path,
            offset,
            limit,
            full,
        )


@R.register("delete_workspace_entry_step")
class DeleteWorkspaceEntryStep(BaseStep):
    """Delete one file or directory after workspace-boundary validation."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            _delete_entry, workspace_root(self.app_config.workspace_dir), self.context["path"]
        )


@R.register("delete_workspace_entries_step")
class DeleteWorkspaceEntriesStep(BaseStep):
    """Delete multiple validated workspace entries in one request."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            _delete_entries,
            workspace_root(self.app_config.workspace_dir),
            self.context["paths"],
        )
