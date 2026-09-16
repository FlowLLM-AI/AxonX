"""Transactional startup and reverse-order shutdown for application objects."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..components.base import BaseComponent
from ..components.graph import ComponentGraph
from ..components.job import BaseJob


class LifecycleManager:
    """Start components and Jobs, rolling back every successfully started object."""

    def __init__(
        self,
        graph: ComponentGraph,
        jobs: Mapping[str, BaseJob],
        workspace: str | Path,
    ) -> None:
        self._graph = graph
        self._jobs = jobs
        self._workspace = Path(workspace).expanduser()
        self._started: list[BaseComponent] = []

    async def start(self) -> None:
        """Start the graph followed by Jobs and roll back on failure."""
        self._workspace.mkdir(parents=True, exist_ok=True)
        try:
            for component in self._graph.startup_order():
                await component.start()
                self._started.append(component)
            for job in sorted(self._jobs.values(), key=lambda item: item.startup_priority):
                await job.start()
                self._started.append(job)
        except BaseException as start_error:
            try:
                await self.close()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "Application startup failed and rollback was incomplete",
                    [start_error, cleanup_error],
                ) from None
            raise

    async def close(self) -> None:
        """Close every started object in reverse order and aggregate failures."""
        errors: list[Exception] = []
        while self._started:
            try:
                await self._started.pop().close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Application cleanup failed", errors)
