"""Task manager interfaces and local process implementation."""

from .base_task_manager import BaseTaskManager
from .local_task_manager import LocalTaskManager

__all__ = ["BaseTaskManager", "LocalTaskManager"]
