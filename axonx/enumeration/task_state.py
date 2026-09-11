"""Lifecycle states for synchronous task runs."""

from enum import StrEnum


class TaskState(StrEnum):
    """Represent the durable lifecycle state of a task run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether no further execution transition is expected."""
        return self not in {TaskState.QUEUED, TaskState.RUNNING}
