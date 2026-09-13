"""Deliver Task status snapshots without blocking Task steps."""

from __future__ import annotations

import asyncio
import os
from queue import Queue
from threading import Thread

from ..components.client import HttpClient
from ..constants import AXONX_SERVICE_INFO
from ..schema import TaskStatus


class TaskStatusReporter:
    """Default no-op status reporter."""

    def __enter__(self):
        return self

    def publish(self, status: TaskStatus) -> None:
        """Publish one complete status snapshot."""

    def __exit__(self, *_exc) -> None:
        pass


class HttpTaskStatusReporter(TaskStatusReporter):
    """Post status snapshots on a dedicated lightweight thread."""

    def __init__(self, logger) -> None:
        self._logger = logger
        self._queue: Queue[TaskStatus | None] = Queue()
        self._thread: Thread | None = None

    def __enter__(self):
        thread = Thread(target=self._write, name="task-status", daemon=True)
        self._thread = thread
        thread.start()
        return self

    def publish(self, status: TaskStatus) -> None:
        self._queue.put(status)

    def __exit__(self, *_exc) -> None:
        self._queue.put(None)
        assert self._thread is not None
        self._thread.join()

    def _write(self) -> None:
        try:
            asyncio.run(self._write_async())
        except Exception as exc:
            self._logger.warning(f"Task status reporter failed: {exc}")

    async def _write_async(self) -> None:
        async with HttpClient() as client:
            while (status := self._queue.get()) is not None:
                try:
                    await client.set_status(status)
                except Exception as exc:
                    self._logger.warning(f"Task status update failed: {exc}")


def create_task_status_reporter(logger) -> TaskStatusReporter:
    """Create the reporter required by the current process environment."""
    if os.environ.get(AXONX_SERVICE_INFO):
        return HttpTaskStatusReporter(logger)
    return TaskStatusReporter()
