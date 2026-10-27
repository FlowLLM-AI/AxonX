"""Public application facade and composition-root lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...client.events import JobEvent
from ...client.models import JobResponse
from ...utils.async_work import run_blocking
from ...utils.logging import LOG_CLEANUP_INTERVAL, cleanup_log_files, get_logger
from ..components.base import BaseComponent
from ..config.models import ApplicationConfig
from ..workspace.core import Workspace
from .composition import compose_application

if TYPE_CHECKING:
    from ...task.runtime.catalog import TaskCatalog
    from ..components.cron.base import ScheduledLaunch
    from ..components.updater.base import UpdateBackend


class Application:
    """Own one isolated component graph and expose Job invocation."""

    def __init__(
        self,
        *,
        providers: Iterable[type] = (),
        workspace: Workspace | None = None,
        updates: UpdateBackend | None = None,
        task_catalog: TaskCatalog | None = None,
        launch_scheduled: ScheduledLaunch | None = None,
        **config: Any,
    ) -> None:
        self.context, self._startup_order = compose_application(
            ApplicationConfig(**config),
            providers=providers,
            workspace=workspace,
            updates=updates,
            task_catalog=task_catalog,
            launch_scheduled=launch_scheduled,
        )
        self._started: list[BaseComponent] = []
        self._lifecycle_lock = asyncio.Lock()
        self.is_started = False
        self._log_cleanup_task: asyncio.Task[None] | None = None

    @property
    def app_config(self) -> ApplicationConfig:
        return self.context.app_config

    @property
    def workspace(self) -> Workspace:
        return self.context.workspace

    @property
    def workspace_path(self) -> Path:
        return self.workspace.root

    async def start(self) -> None:
        """Start the complete runtime or roll back every successful start."""
        async with self._lifecycle_lock:
            if self.is_started:
                return
            self.workspace.ensure()
            self.context.metadata.pop("stopping", None)
            try:
                for component in self._startup_order:
                    await component.start()
                    self._started.append(component)
            except BaseException as start_error:
                self.request_shutdown()
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
            try:
                await run_blocking(cleanup_log_files, directory)
            except Exception:
                get_logger("Application").exception("Log cleanup failed; retrying at the next interval")
            await asyncio.sleep(LOG_CLEANUP_INTERVAL)

    async def close(self) -> None:
        """Close every started object in reverse order, without short-circuiting."""
        async with self._lifecycle_lock:
            self.is_started = False
            errors: list[BaseException] = []
            try:
                self.request_shutdown()
            except BaseException as exc:  # noqa: BLE001 - cleanup must continue.
                errors.append(exc)
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
            if errors:
                raise BaseExceptionGroup("Application cleanup failed", errors)

    def request_shutdown(self) -> None:
        """Mark the application as stopping before resource cleanup."""
        self.context.metadata["stopping"] = True

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
        self._require_running()
        return await self.context.dispatcher.run(name, arguments, target=target)

    def stream_job(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        target: str | None = None,
    ) -> AsyncIterator[JobEvent]:
        self._require_running()
        return self.context.dispatcher.stream(name, arguments, target=target)

    def _require_running(self) -> None:
        if not self.is_started or self.context.metadata.get("stopping"):
            raise RuntimeError("Application is not running")

    async def __aenter__(self) -> Application:
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
