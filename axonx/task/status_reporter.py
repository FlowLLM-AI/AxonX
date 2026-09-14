"""Deliver Task status snapshots without blocking Task steps."""

from __future__ import annotations

import asyncio
from collections import deque
import os
from threading import Condition, Thread

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
        self._pending: deque[TaskStatus] = deque()
        self._condition = Condition()
        self._closed = False
        self._thread: Thread | None = None

    def __enter__(self):
        thread = Thread(target=self._write, name="task-status", daemon=True)
        self._thread = thread
        thread.start()
        return self

    def publish(self, status: TaskStatus) -> None:
        with self._condition:
            if self._pending and self._same_progress(self._pending[-1], status):
                self._pending[-1] = status
            else:
                self._pending.append(status)
            self._condition.notify()

    def __exit__(self, *_exc) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify()
        assert self._thread is not None
        self._thread.join()

    @staticmethod
    def _same_progress(previous: TaskStatus, current: TaskStatus) -> bool:
        """Return whether two queued snapshots differ only by active progress."""
        if (
            previous.task_id != current.task_id
            or previous.state != current.state
            or previous.state.is_terminal
            or len(previous.steps) != len(current.steps)
            or not current.steps
        ):
            return False
        left, right = previous.steps[-1], current.steps[-1]
        return (
            left.name == right.name
            and left.finished_at is None
            and right.finished_at is None
            and left.percentage is not None
            and right.percentage is not None
        )

    def _next(self) -> TaskStatus | None:
        with self._condition:
            self._condition.wait_for(lambda: self._pending or self._closed)
            return self._pending.popleft() if self._pending else None

    def _write(self) -> None:
        try:
            asyncio.run(self._write_async())
        except Exception as exc:
            self._logger.warning(f"Task status reporter failed: {exc}")

    async def _write_async(self) -> None:
        async with HttpClient() as client:
            while (status := self._next()) is not None:
                try:
                    await client.set_status(status)
                except Exception as exc:
                    self._logger.warning(f"Task status update failed: {exc}")


def create_task_status_reporter(logger) -> TaskStatusReporter:
    """Create the reporter required by the current process environment."""
    if os.environ.get(AXONX_SERVICE_INFO):
        return HttpTaskStatusReporter(logger)
    return TaskStatusReporter()
