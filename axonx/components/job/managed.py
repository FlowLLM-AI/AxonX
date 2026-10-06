"""Own submitted workers through cancellation and service shutdown."""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from collections.abc import AsyncIterator, Mapping
from typing import Any

from .base import BaseJob
from .contracts import JobResponse
from .events import JobEvent, ResultEvent
from ..task_manager.base import BaseTaskManager
from ...task.contracts import TaskHandle
from ...task.runtime.arguments import build_task_argv
from ...task.storage.workspace import TaskStatus


class TaskStageError(Exception):
    """Keep the submitted Run and both execution and cleanup failures."""

    def __init__(self, handle: TaskHandle | None, cause: BaseException, cleanup_error: Exception | None = None):
        self.handle = handle
        self.cause = cause
        self.cleanup_error = cleanup_error
        identity = f" task_id={handle.task_id} run_id={handle.run_id}" if handle else ""
        detail = f"{type(cause).__name__}: {cause}"
        if cleanup_error is not None:
            detail += f"; cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}"
        super().__init__(detail + identity)


class ManagedTaskJob(BaseJob):
    def __init__(self, poll_interval: float = 1.0, task_manager: str = "default", **kwargs: Any):
        super().__init__(**kwargs)
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.poll_interval = poll_interval
        self._manager_name = task_manager
        self._manager: BaseTaskManager | None = None
        self._executions: set[asyncio.Task[Any]] = set()
        self._cleanup_errors: list[TaskStageError] = []
        self._accepting = False

    @property
    def manager(self) -> BaseTaskManager:
        if self._manager is None:
            manager = self.get_component("task_manager", self._manager_name)
            if not isinstance(manager, BaseTaskManager):
                raise TypeError("Task Job requires a Task manager")
            self._manager = manager
        return self._manager

    @manager.setter
    def manager(self, manager: BaseTaskManager) -> None:
        self._manager = manager

    async def _start(self) -> None:
        self._accepting = True

    async def _close(self) -> None:
        self._accepting = False
        active = tuple(self._executions)
        for task in active:
            task.cancel()
        results = await asyncio.gather(*active, return_exceptions=True)
        errors = [*self._cleanup_errors, *(result for result in results if isinstance(result, Exception))]
        if errors:
            raise ExceptionGroup("Task Job cleanup failed", errors)

    # Async generators implement the base contract returning an AsyncIterator.
    async def stream(  # pylint: disable=invalid-overridden-method
        self, arguments: Mapping[str, Any], system: Mapping[str, Any]
    ) -> AsyncIterator[JobEvent]:
        if not self._accepting:
            raise RuntimeError("Task Job is not running")
        task = asyncio.current_task()
        assert task is not None
        self._executions.add(task)
        try:
            response = await self.execute(arguments)
        except Exception as exc:
            response = JobResponse().fail(exc)
        finally:
            self._executions.discard(task)
        yield ResultEvent.from_response(response)

    @abstractmethod
    async def execute(self, arguments: Mapping[str, Any]) -> JobResponse:
        """Compose submitted Tasks into one Job response."""

    async def run_stage(self, name: str, config: Mapping[str, Any]) -> TaskStatus:
        # Retain submission ownership even if cancellation arrives before the handle.
        try:
            arguments = build_task_argv(name, config)
        except (ValueError, TypeError) as cause:
            raise TaskStageError(None, cause) from cause
        submission = asyncio.create_task(self.manager.submit(arguments))
        handle: TaskHandle | None = None
        try:
            handle = await asyncio.shield(submission)
            return await self.manager.wait(handle.task_id, handle.run_id, self.poll_interval)
        except BaseException as cause:

            async def stop() -> None:
                nonlocal handle
                handle = handle or await submission
                # A normal return guarantees this exact Run has stopped; no second polling race.
                await self.manager.cancel(run_id=handle.run_id)

            # A failed submission never transferred a worker handle to this Job.
            if submission.done() and not submission.cancelled() and submission.exception() is not None:
                if isinstance(cause, asyncio.CancelledError):
                    raise cause from submission.exception()
                raise TaskStageError(None, cause) from cause
            cleanup = asyncio.create_task(stop())
            try:
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
            except Exception as cleanup_error:
                if handle is None and submission.done() and submission.exception() is cleanup_error:
                    raise cause from cleanup_error
                error = TaskStageError(handle, cause, cleanup_error)
                self._cleanup_errors.append(error)
                raise error from cause
            if not isinstance(cause, Exception):
                raise
            raise TaskStageError(handle, cause) from cause
