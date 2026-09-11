"""Component contract for managing synchronous Task runs."""

from abc import ABC, abstractmethod

from ...enumeration import ComponentEnum
from ..base_component import BaseComponent
from ...schema import TaskStatus


class BaseTaskManager(BaseComponent, ABC):
    """Define asynchronous management operations for isolated task runs."""

    component_type = ComponentEnum.TASK_MANAGER

    @abstractmethod
    async def submit(self, task: str, config: dict | None = None, *, suffix: str | None = None) -> str:
        """Submit a task and return its identifier."""

    @abstractmethod
    async def list_task_ids(self) -> list[str]:
        """Return all known task identifiers."""

    @abstractmethod
    async def get_status(self, task_id: str) -> TaskStatus:
        """Return one task status snapshot."""

    @abstractmethod
    async def cancel(self, task_id: str) -> TaskStatus:
        """Cancel a queued task or kill its running worker."""

    @abstractmethod
    async def wait(self, task_id: str, timeout: float | None = None) -> TaskStatus:
        """Wait for a task without cancelling it on timeout."""

    @abstractmethod
    async def logs(self, task_id: str, limit: int = 65536) -> str:
        """Read at most the trailing ``limit`` bytes of a task log."""
