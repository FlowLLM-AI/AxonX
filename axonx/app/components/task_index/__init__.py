"""Application Task metadata index contract."""

from .base import BaseTaskIndex
from .local import LocalTaskIndex

__all__ = ["BaseTaskIndex", "LocalTaskIndex"]
