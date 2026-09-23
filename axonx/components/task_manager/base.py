"""Component contract for asynchronously managing task runs."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from ...components.job.events import JobEvent
from ...enums import ComponentEnum
from ...task.contracts import TaskHandle
from ...task.query.graph import TaskGraph
from ...task.storage.events import LOG_WINDOW_BYTES, TaskLogChunk
from ...task.storage.workspace import TaskStatus
from ..base import BaseComponent


class BaseTaskManager(BaseComponent, ABC):
    """Define asynchronous management operations for isolated task runs."""

    component_type = ComponentEnum.TASK_MANAGER

    @abstractmethod
    async def submit(self, argv: Sequence[str]) -> TaskHandle:
        """Create a queued Task, start its worker, and return its stable handle."""

    async def list_ids(self) -> list[str]:
        """Return the IDs of every task with a status, newest first."""
        return [status.task_id for status in await self.list_statuses()]

    @abstractmethod
    async def list_statuses(self) -> list[TaskStatus]:
        """Return snapshots from status files, newest first."""

    @abstractmethod
    async def get_status(self, task_id: str) -> TaskStatus:
        """Return one task status; raise KeyError if the ID is absent."""

    async def wait(
        self, task_id: str, run_id: str, poll_interval: float = 1.0
    ) -> TaskStatus:
        """Wait for one specific run to finish and return its final status."""
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        while True:
            status = await self.get_status(task_id)
            if status.run_id != run_id:
                raise ValueError(f"Task run changed: {task_id}")
            if status.state.is_terminal:
                return status
            await asyncio.sleep(poll_interval)

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """Stop a managed worker and persist cancellation; return whether it stopped."""

    @abstractmethod
    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        """Delete terminal task directories and return their IDs."""

    @abstractmethod
    async def get_graph(self, task_id: str) -> TaskGraph:
        """Return the graph containing one task; raise KeyError if absent."""

    @abstractmethod
    async def read_log(
        self, task_id: str, offset: int = -1, limit: int = LOG_WINDOW_BYTES
    ) -> TaskLogChunk:
        """Read a bounded range of a task log; raise KeyError if the ID is absent."""

    @abstractmethod
    def stream(
        self, task_id: str, poll_interval: float = 0.5
    ) -> AsyncIterator[JobEvent]:
        """Follow one task until it stops, emitting its progress and log.

        The stream carries only what happened — ``ProgressEvent`` and ``LogEvent`` — and
        ends when the task reaches a terminal state. The outcome is the task's
        own final ``TaskStatus``, which the caller reads afterwards, so a job
        built on this stream still ends in exactly one terminal ``ResultEvent``.
        """
