"""Public application facade and composition-root lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping
from pathlib import Path
from typing import Any

from .._version import VERSION
from ..components.base import BaseComponent
from ..components.job.contracts import JobResponse
from ..components.job.events import JobEvent
from ..components.registry import ProviderRegistry
from ..config import ApplicationConfig
from ..utils.async_work import run_blocking
from ..utils.log_retention import LOG_CLEANUP_INTERVAL, cleanup_log_files
from ..utils.logging import get_logger
from .composition import compose_application
from .context import ApplicationContext
from .graph import ComponentGraph


class Application:
    """Own one isolated component graph and expose Job invocation."""

    def __init__(self, *, providers: Iterable[type] = (), **config: Any) -> None:
        registry = ProviderRegistry.from_builtins()
        for implementation in providers:
            registry.add(implementation)
        self.context: ApplicationContext = compose_application(registry, VERSION, config)
        self._startup_order = ComponentGraph(self.context.components).resolve()
        self._started: list[BaseComponent] = []
        self._lifecycle_lock = asyncio.Lock()
        self.is_started = False
        self._log_cleanup_task: asyncio.Task[None] | None = None

    @property
    def app_config(self) -> ApplicationConfig:
        return self.context.app_config

    @property
    def workspace_path(self) -> Path:
        return Path(self.app_config.workspace_dir).expanduser()

    async def start(self) -> None:
        """Start the complete runtime or roll back every successful start."""
        async with self._lifecycle_lock:
            if self.is_started:
                return
            self.workspace_path.mkdir(parents=True, exist_ok=True)
            self.context.metadata.pop("stopping", None)
            try:
                for component in self._startup_order:
                    await component.start()
                    self._started.append(component)
                for job in self.context.jobs.values():
                    await job.start()
                    self._started.append(job)
                for scheduler in self.context.schedulers.values():
                    await scheduler.start()
                    self._started.append(scheduler)
            except BaseException as start_error:
                cleanup_errors = await self._close_started()
                if cleanup_errors:
                    raise BaseExceptionGroup(
                        "Application startup failed and rollback was incomplete",
                        [start_error, *cleanup_errors],
                    ) from None
                raise
            self.is_started = True
            if self.app_config.log_to_file:
                self._log_cleanup_task = asyncio.create_task(self._maintain_logs(), name="axonx-log-cleanup")

    async def _maintain_logs(self) -> None:
        directory = Path(self.app_config.log_dir).expanduser().resolve()
        while True:
            await asyncio.sleep(LOG_CLEANUP_INTERVAL)
            try:
                await run_blocking(cleanup_log_files, directory)
            except Exception:
                get_logger("Application").exception("Log cleanup failed; retrying at the next interval")

    async def close(self) -> None:
        """Close every started object in reverse order, without short-circuiting."""
        async with self._lifecycle_lock:
            self.context.metadata["stopping"] = True
            errors: list[BaseException] = []
            if self._log_cleanup_task is not None:
                self._log_cleanup_task.cancel()
                try:
                    await self._log_cleanup_task
                except asyncio.CancelledError:
                    pass
                except BaseException as exc:  # noqa: BLE001 - cleanup must continue.
                    errors.append(exc)
                self._log_cleanup_task = None
            errors.extend(await self._close_started())
            self.is_started = False
            if errors:
                raise BaseExceptionGroup("Application cleanup failed", errors)

    async def _close_started(self) -> list[BaseException]:
        errors: list[BaseException] = []
        while self._started:
            try:
                await self._started.pop().close()
            except BaseException as exc:  # noqa: BLE001 - cleanup must continue.
                errors.append(exc)
        return errors

    async def run_job(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        target: str | None = None,
    ) -> JobResponse:
        if not self.is_started:
            raise RuntimeError("Application is not running")
        return await self.context.dispatcher.run(name, arguments, target=target)

    def stream_job(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        target: str | None = None,
    ) -> AsyncIterator[JobEvent]:
        if not self.is_started:
            raise RuntimeError("Application is not running")
        return self.context.dispatcher.stream(name, arguments, target=target)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.close()
