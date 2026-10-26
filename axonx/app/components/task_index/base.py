"""Contract for Task metadata queries and local change notifications."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable

from ....task.models.events import LogChunk, TaskEvent
from ....task.models.lifecycle import TaskMetadata
from ....task.models.query import TaskContextSnapshot, TaskGraph, TaskSummary
from ..base import BaseComponent
from ..component_type import ComponentType

TaskChangeCallback = Callable[[frozenset[str]], None]


class BaseTaskIndex(BaseComponent, ABC):
    """Maintain queryable Task snapshots and notify local consumers of changes."""

    component_type = ComponentType.TASK_INDEX

    @abstractmethod
    def subscribe(self, callback: TaskChangeCallback) -> Callable[[], None]:
        """Register a change callback and return its unsubscribe function."""

    @abstractmethod
    async def entry(self, task_id: str) -> TaskMetadata:
        """Read fresh metadata for one task or raise KeyError."""

    @abstractmethod
    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> dict[str, TaskMetadata]:
        """Return isolated snapshots of matching indexed records."""

    @abstractmethod
    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        """Project lightweight summaries from the index, newest first."""

    @abstractmethod
    async def graph(self, task_id: str) -> TaskGraph:
        """Build task relationships from indexed records."""

    @abstractmethod
    async def context(self, task_id: str) -> TaskContextSnapshot:
        """Project one Task's status and relationships for an Agent."""

    @abstractmethod
    async def read_log(self, status: TaskMetadata, offset: int, limit: int) -> LogChunk:
        """Read a bounded log chunk for an exact Task snapshot."""

    @abstractmethod
    def stream(self, task_id: str, poll_interval: float) -> AsyncIterator[TaskEvent]:
        """Follow Task progress and logs until the execution is terminal."""
