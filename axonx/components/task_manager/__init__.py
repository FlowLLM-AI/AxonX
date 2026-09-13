"""Task manager interfaces and local process implementation."""

from .base import BaseTaskManager
from .local import LocalTaskManager

__all__ = ["BaseTaskManager", "LocalTaskManager"]
