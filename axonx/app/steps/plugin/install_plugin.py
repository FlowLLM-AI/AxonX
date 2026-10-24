"""Install a plugin wheel already copied into the local workspace."""

from ....plugin.registry import provider
from ....common.async_work import run_blocking
from ....plugin import install_staged_plugin
from ...workspace.staging import StagedFiles
from ..base import BaseStep


@provider("install_plugin_step")
class InstallPluginStep(BaseStep):
    """Validate and install one staged wheel on this service machine."""

    async def execute(self):
        path = self.context["path"]
        sha256 = self.context["sha256"]
        staged_files = StagedFiles(
            self.workspace_path,
            transfer_budget_bytes=self.app_config.transfer_budget_bytes,
        )
        staged = staged_files.file(path)
        try:
            artifact_directory = self.workspace_path / "plugins" / "artifacts"
            self.response.answer = await run_blocking(
                install_staged_plugin,
                staged,
                sha256,
                artifact_directory,
            )
        finally:
            await run_blocking(staged_files.discard, path)
