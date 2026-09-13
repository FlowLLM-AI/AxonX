"""Component contract for managing synchronous Task runs."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ...enums import ComponentEnum
from ..base import BaseComponent
from ...schema import TaskStatus


class BaseTaskManager(BaseComponent, ABC):
    """Define asynchronous management operations for isolated task runs."""

    component_type = ComponentEnum.TASK_MANAGER

    @abstractmethod
    async def submit(self, argv: Sequence[str]) -> None:
        """Start ``axonx exec`` with the supplied arguments."""

    @abstractmethod
    async def set_status(self, task_id: str, status: TaskStatus) -> None:
        """Store a complete status reported by a task worker."""

    @abstractmethod
    async def list_runtime_task_ids(self) -> list[str]:
        """Return all known runtime task identifiers."""

    @abstractmethod
    async def list_runtime_task_statuses(self) -> list[TaskStatus]:
        """Return snapshots for all known task executions."""

    @abstractmethod
    async def get_status(self, task_id: str) -> TaskStatus:
        """Return one task status."""

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """Return whether cancellation was successfully requested."""

    @abstractmethod
    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        """Delete terminal task records and return the IDs that were deleted."""
