"""Workspace Job adapters and legacy helper imports."""

import asyncio
from pathlib import Path

from ...components.registry import R
from ...workspace.listing import list_entries as _list_entries
from ...workspace.operations import (
    delete_entries as _delete_entries,
    delete_entry as _delete_entry,
)
from ...workspace.preview import CSV_PREVIEW_ROWS, preview_file as _preview_file
from ..base import BaseStep


def _workspace_root(step: BaseStep) -> Path:
    return Path(step.app_config.workspace_dir).expanduser().resolve()


@R.register("list_workspace_entries_step")
class ListWorkspaceEntriesStep(BaseStep):
    """List one directory without walking the complete workspace tree."""

    async def execute(self):
        relative_path = self.context.get("path", "")
        self.response.answer = await asyncio.to_thread(_list_entries, _workspace_root(self), relative_path)


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
            _workspace_root(self),
            relative_path,
            offset,
            limit,
            full,
        )


@R.register("delete_workspace_entry_step")
class DeleteWorkspaceEntryStep(BaseStep):
    """Delete one file or directory after workspace-boundary validation."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(_delete_entry, _workspace_root(self), self.context["path"])


@R.register("delete_workspace_entries_step")
class DeleteWorkspaceEntriesStep(BaseStep):
    """Delete multiple validated workspace entries in one request."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            _delete_entries,
            _workspace_root(self),
            self.context["paths"],
        )
