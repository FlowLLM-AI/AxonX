"""Package-version step."""

from ...core.build_info import get_build_info
from ..base import BaseStep
from ...registry import provider


@provider("version_step")
class VersionStep(BaseStep):
    """Expose the installed AxonX version."""

    async def execute(self):
        version = get_build_info().version
        self.logger.info(f"[{self.name}] version={version}")
        self.response.answer = version
        self.response.metadata["version"] = version
