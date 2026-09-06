"""Synchronous task base types and dependency-free built-in tasks."""

from .base_task import BaseConfig, BaseTask

# Import the dependency-free built-in task before AxonX freezes its registry.
from .common import DemoTask

__all__ = ["BaseConfig", "BaseTask", "DemoTask"]
