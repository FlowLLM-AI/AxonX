"""Return the package version."""

from ..base_step import BaseStep

from ...components import R


@R.register("version_step")
class VersionStep(BaseStep):
    """Emit axonx.__version__ as the response answer."""

    async def execute(self):
        from ... import __version__

        self.logger.info(f"[{self.name}] version={__version__}")
        self.response.answer = __version__
        self.response.metadata["version"] = __version__
