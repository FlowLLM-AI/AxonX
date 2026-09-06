"""Lifecycle states for synchronous task runs."""

from enum import StrEnum


class TaskState(StrEnum):
    """Represent the durable lifecycle state of a task run."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"

    @property
    def is_terminal(self) -> bool:
        """Whether no further execution transition is expected."""
        return self in _TERMINAL_TASK_STATES


_TERMINAL_TASK_STATES = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.LOST,
    },
)
