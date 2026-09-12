"""Package-version step."""

from ...components import R
from .base_step import BaseStep


@R.register("version_step")
class VersionStep(BaseStep):
    """Expose the installed AxonX version."""

    async def execute(self):
        from ... import __version__

        self.logger.info(f"[{self.name}] version={__version__}")
        self.response.answer = __version__
        self.response.metadata["version"] = __version__
