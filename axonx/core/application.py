"""Public application facade."""

from __future__ import annotations

from typing import Any

from .. import __version__
from ..components.base import BaseComponent
from ..components.graph import ComponentGraph
from ..components.registry import R
from .builder import ApplicationBuilder
from .context import ApplicationContext
from .dispatch import JobDispatcher
from .lifecycle import LifecycleManager


class Application(BaseComponent):
    """Expose application lifecycle, context, and Job invocation."""

    def __init__(self, **config: Any) -> None:
        self.context: ApplicationContext = ApplicationBuilder(R, __version__, **config).build()
        super().__init__(app_context=self.context)
        self._lifecycle = LifecycleManager(
            ComponentGraph(self.context.components),
            self.context.jobs,
            self.app_config.workspace_dir,
        )
        self._dispatcher = JobDispatcher(self.context)

    async def _start(self) -> None:
        await self._lifecycle.start()

    async def _close(self) -> None:
        self.is_started = False
        await self._lifecycle.close()

    async def run_job(self, name: str, **kwargs: Any) -> Any:
        """Run a public job."""
        if not self.is_started:
            raise RuntimeError("Application is not running")
        return await self._dispatcher.run(name, **kwargs)
