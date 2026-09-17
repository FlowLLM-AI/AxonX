"""Component contract for task artifact dependency graphs."""

from abc import ABC, abstractmethod
from typing import Any

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseTaskGraphComponent(BaseComponent, ABC):
    """Define asynchronous task graph queries."""

    component_type = ComponentEnum.TASK_GRAPH

    @abstractmethod
    async def list_graphs(self, query: str = "", offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """Return a paginated list of task graphs matching the query."""

    @abstractmethod
    async def get_graph(self, task_id: str) -> dict[str, Any]:
        """Return the full graph containing a task artifact."""
