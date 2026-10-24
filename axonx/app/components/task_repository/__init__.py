"""Stateful access to the local Task workspace."""

from .base import BaseTaskRepository
from .local import LocalTaskRepository
from .subscription import TaskChanges, TaskChangeSubscription

__all__ = [
    "BaseTaskRepository",
    "LocalTaskRepository",
    "TaskChangeSubscription",
    "TaskChanges",
]
