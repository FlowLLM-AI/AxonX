"""Compatibility exports for synchronous Task composition."""

from .core.composite import BaseCompositeTask, ChildTaskError, ChildTaskResult

__all__ = ["BaseCompositeTask", "ChildTaskError", "ChildTaskResult"]
