"""Component contract for managing synchronous Task runs."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ...enumeration import ComponentEnum
from ..base_component import BaseComponent
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
    async def list_task_ids(self) -> list[str]:
        """Return all known task identifiers."""

    @abstractmethod
    async def get_status(self, task_id: str) -> TaskStatus:
        """Return one task status."""

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """Return whether cancellation was successfully requested."""
