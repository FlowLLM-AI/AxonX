"""Contract for Task metadata queries and local change notifications."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..base import BaseComponent
from ..component_type import ComponentType
from ....task.models.lifecycle import TaskMetadata
from ....task.models.query import TaskGraph, TaskSummary

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
