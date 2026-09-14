"""Deliver Task status snapshots without blocking Task steps."""

from __future__ import annotations

import asyncio
from collections import deque
import math
import os
from threading import Condition, Thread
from time import monotonic

from ..components.client import HttpClient
from ..constants import (
    AXONX_DEFAULT_TASK_STATUS_MIN_INTERVAL,
    AXONX_SERVICE_INFO,
    AXONX_TASK_STATUS_MIN_INTERVAL,
)
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

    def __init__(
        self,
        logger,
        min_interval: float = AXONX_DEFAULT_TASK_STATUS_MIN_INTERVAL,
    ) -> None:
        if not math.isfinite(min_interval) or min_interval < 0:
            raise ValueError("min_interval must be a finite non-negative number")
        self._logger = logger
        self._min_interval = min_interval
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

    def _next(self, not_before: float = 0) -> TaskStatus | None:
        with self._condition:
            while True:
                if not self._pending:
                    if self._closed:
                        return None
                    self._condition.wait()
                    continue
                remaining = not_before - monotonic()
                if remaining <= 0:
                    return self._pending.popleft()
                # Releasing the condition while throttled lets publishers
                # replace queued progress snapshots with the newest value.
                self._condition.wait(timeout=remaining)

    def _write(self) -> None:
        try:
            asyncio.run(self._write_async())
        except Exception as exc:
            self._logger.warning(f"Task status reporter failed: {exc}")

    async def _write_async(self) -> None:
        async with HttpClient() as client:
            next_send_at = 0.0
            while (status := self._next(next_send_at)) is not None:
                send_started_at = monotonic()
                try:
                    await client.set_status(status)
                except Exception as exc:
                    self._logger.warning(f"Task status update failed: {exc}")
                next_send_at = send_started_at + self._min_interval


def _status_min_interval(logger) -> float:
    value = os.environ.get(AXONX_TASK_STATUS_MIN_INTERVAL)
    if value is None:
        return AXONX_DEFAULT_TASK_STATUS_MIN_INTERVAL
    try:
        interval = float(value)
        if not math.isfinite(interval) or interval < 0:
            raise ValueError
        return interval
    except ValueError:
        logger.warning(
            f"Invalid {AXONX_TASK_STATUS_MIN_INTERVAL} value: {value}; "
            f"using {AXONX_DEFAULT_TASK_STATUS_MIN_INTERVAL:g} seconds",
        )
        return AXONX_DEFAULT_TASK_STATUS_MIN_INTERVAL


def create_task_status_reporter(logger) -> TaskStatusReporter:
    """Create the reporter required by the current process environment."""
    if os.environ.get(AXONX_SERVICE_INFO):
        return HttpTaskStatusReporter(logger, _status_min_interval(logger))
    return TaskStatusReporter()
