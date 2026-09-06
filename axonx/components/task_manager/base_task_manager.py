"""Component contract for managing synchronous Task runs."""

from abc import ABC, abstractmethod

from ...enumeration import ComponentEnum
from ..base_component import BaseComponent
from ...schema import TaskRun


class BaseTaskManager(BaseComponent, ABC):
    """Define asynchronous management operations for isolated task runs."""

    component_type = ComponentEnum.TASK_MANAGER

    @abstractmethod
    async def submit(self, task: str, config: dict | None = None) -> str:
        """Submit a task and return its new run identifier."""

    @abstractmethod
    async def status(self, run_id: str | None = None) -> TaskRun | list[TaskRun]:
        """Return one run snapshot or all known runs."""

    @abstractmethod
    async def wait(self, run_id: str, timeout: float | None = None) -> TaskRun:
        """Wait for a run to finish without cancelling it on timeout."""

    @abstractmethod
    async def cancel(self, run_id: str) -> TaskRun:
        """Request cooperative cancellation of a run."""

    @abstractmethod
    async def kill(self, run_id: str) -> TaskRun:
        """Force a run and its process group to stop."""

    @abstractmethod
    async def logs(self, run_id: str, limit: int = 65536) -> str:
        """Read at most the trailing ``limit`` bytes of a run log."""

    @abstractmethod
    async def report_progress(self, run_id: str, step_index: int, task_step: dict) -> TaskRun:
        """Store a monotonic progress update for one task step."""
