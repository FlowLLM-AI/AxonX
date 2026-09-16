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


class Application(BaseComponent):
    """Expose application lifecycle, context, and Job invocation."""

    def __init__(self, **config: Any) -> None:
        self.context: ApplicationContext = ApplicationBuilder(R, __version__, **config).build()
        super().__init__(app_context=self.context)
        self._graph = ComponentGraph(self.context.components)
        self._started: list[BaseComponent] = []
        self._dispatcher = JobDispatcher(self.context)

    async def _start(self) -> None:
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        try:
            for component in self._graph.startup_order():
                await component.start()
                self._started.append(component)
            for job in sorted(self.context.jobs.values(), key=lambda item: item.startup_priority):
                await job.start()
                self._started.append(job)
        except BaseException as start_error:
            try:
                await self._close()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "Application startup failed and rollback was incomplete",
                    [start_error, cleanup_error],
                ) from None
            raise

    async def _close(self) -> None:
        errors: list[Exception] = []
        while self._started:
            try:
                await self._started.pop().close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Application cleanup failed", errors)

    async def run_job(self, name: str, **kwargs: Any) -> Any:
        """Run a public job."""
        if not self.is_started:
            raise RuntimeError("Application is not running")
        return await self._dispatcher.run(name, **kwargs)
