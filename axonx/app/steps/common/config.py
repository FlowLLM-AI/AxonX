"""Expose resolved application configuration without runtime callbacks."""

from pathlib import Path

from ...registry import provider
from ..base import BaseStep


@provider("get_config_step")
class GetConfigStep(BaseStep):
    """Return the running configuration with execution paths resolved here."""

    async def execute(self):
        config = self.app_config.model_dump(
            mode="json",
            exclude={"components": {"cron": {"__all__": {"launch", "validate_command"}}}},
        )
        config["workspace_dir"] = str(self.workspace.root)
        config["log_dir"] = str(Path(self.app_config.log_dir).expanduser().resolve())
        self.response.answer = config
