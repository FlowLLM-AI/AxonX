"""Install a plugin wheel already copied into the local workspace."""

import asyncio

from ...components.registry import provider
from ...plugin_kit import install_staged_plugin
from ...workspace.staging import StagedFiles
from ..base import BaseStep


@provider("install_plugin_step")
class InstallPluginStep(BaseStep):
    """Validate and install one staged wheel on this service machine."""

    async def execute(self):
        path = self.context["path"]
        sha256 = self.context["sha256"]
        staged_files = StagedFiles(self.workspace_path)
        staged = staged_files.file(path)
        try:
            if not self.app_config.plugins.allow_remote_management:
                raise PermissionError("Remote plugin management is disabled")
            artifact_directory = self.workspace_path / "plugins" / "artifacts"
            self.response.answer = await asyncio.to_thread(
                install_staged_plugin,
                staged,
                sha256,
                artifact_directory,
            )
        finally:
            await asyncio.to_thread(staged_files.discard, path)
