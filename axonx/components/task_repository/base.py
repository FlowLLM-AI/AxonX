"""Contract for indexed, observable access to a Task workspace."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path

from ...enums import ComponentEnum
from ...task.query.graph import TaskGraph
from ...task.query.summary import TaskSummary, managed_runs
from ...task.schemas.lifecycle import TaskMetadata
from ...task.sync import SyncTasksReport
from ..base import BaseComponent
from .subscription import TaskChangeSubscription


class BaseTaskRepository(BaseComponent, ABC):
    """Own the live workspace index and broadcast changes to its consumers."""

    component_type = ComponentEnum.TASK_REPOSITORY

    @abstractmethod
    def subscribe(self) -> TaskChangeSubscription:
        """Return an isolated coalescing subscription."""

    @abstractmethod
    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> Mapping[str, TaskMetadata]:
        """Return isolated snapshots of indexed entries."""

    @abstractmethod
    async def entry(self, task_id: str) -> TaskMetadata:
        """Return one indexed entry or raise ``KeyError``."""

    @abstractmethod
    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        """Project isolated lightweight summaries directly from the index, newest first."""

    async def managed_runs(self, owned: set[str]) -> dict[str, str]:
        """Resolve owned roots and their exact in-process child Runs."""
        return managed_runs(await self.entries(), owned)

    @abstractmethod
    async def graph(self, task_id: str) -> TaskGraph:
        """Build a graph under the index lock without copying task outputs."""

    @abstractmethod
    async def put_metadata(self, status: TaskMetadata) -> None:
        """Persist and index a status owned by this application."""

    @abstractmethod
    async def forget(self, task_id: str) -> None:
        """Remove an entry from the index after its directory is gone."""

    @abstractmethod
    async def delete_terminal(self, task_id: str) -> bool:
        """Delete one terminal Task directory under the repository mutation lock."""

    @abstractmethod
    async def reset_terminal(self, task_id: str) -> bool:
        """Clear a terminal Run under the mutation lock, retaining persistent data."""

    @abstractmethod
    async def reconcile(self) -> None:
        """Rebuild the index from disk."""

    @abstractmethod
    async def apply_sync(
        self,
        archive_path: Path | None,
        deletions: list[str],
        archive_name: str | None,
    ) -> SyncTasksReport:
        """Atomically apply remote snapshots while excluding local mutations."""
