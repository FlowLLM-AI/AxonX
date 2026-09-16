"""Workspace deletion Job adapters."""

import asyncio

from ...components.registry import R
from ..base import BaseStep
from .operations import delete_entries as _delete_entries, delete_entry as _delete_entry
from .paths import workspace_root


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
