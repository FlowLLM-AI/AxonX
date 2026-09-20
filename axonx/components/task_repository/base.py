"""Contract for indexed, observable access to a Task workspace."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path

from ...enums import ComponentEnum
from ...task.storage.workspace import TaskEntry, TaskRecord, TaskStatus
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
    async def entries(self) -> Mapping[str, TaskEntry]:
        """Return an immutable snapshot of indexed entries."""

    @abstractmethod
    async def entry(self, task_id: str) -> TaskEntry:
        """Return one indexed entry or raise ``KeyError``."""

    @abstractmethod
    async def statuses(self) -> Mapping[str, TaskStatus]:
        """Return indexed statuses keyed by Task ID."""

    @abstractmethod
    async def records(self) -> Mapping[str, TaskRecord]:
        """Return indexed metadata records keyed by Task ID."""

    @abstractmethod
    async def put_status(self, status: TaskStatus) -> None:
        """Persist and index a status owned by this application."""

    @abstractmethod
    async def forget(self, task_id: str) -> None:
        """Remove an entry from the index after its directory is gone."""

    @abstractmethod
    async def delete_terminal(self, task_id: str) -> bool:
        """Delete one terminal Task directory under the repository mutation lock."""

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
