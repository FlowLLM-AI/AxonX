"""Component contract for asynchronously managing task runs."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ...enums import ComponentEnum
from ...schema import TaskGraph, TaskGraphList, TaskLogChunk, TaskStatus
from ..base import BaseComponent


class BaseTaskManager(BaseComponent, ABC):
    """Define asynchronous management operations for isolated task runs."""

    component_type = ComponentEnum.TASK_MANAGER

    @abstractmethod
    async def submit(self, argv: Sequence[str]) -> None:
        """Start ``axonx exec`` with the supplied arguments."""

    @abstractmethod
    async def list_ids(self) -> list[str]:
        """Return IDs with a status file."""

    @abstractmethod
    async def list_statuses(self) -> list[TaskStatus]:
        """Return snapshots from status files."""

    @abstractmethod
    async def get_status(self, task_id: str) -> TaskStatus:
        """Return one task status; raise KeyError if the ID is absent."""

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """Stop a managed worker and persist cancellation; return whether it stopped."""

    @abstractmethod
    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        """Delete terminal task directories and return their IDs."""

    @abstractmethod
    async def list_graphs(self, query: str = "", offset: int = 0, limit: int = 50) -> TaskGraphList:
        """List task dependency graphs."""

    @abstractmethod
    async def get_graph(self, task_id: str) -> TaskGraph:
        """Return the graph containing one task; raise KeyError if absent."""

    @abstractmethod
    async def read_log(self, task_id: str, offset: int = -1, limit: int = 65_536) -> TaskLogChunk:
        """Read a bounded range of a task log; raise KeyError if the ID is absent."""
