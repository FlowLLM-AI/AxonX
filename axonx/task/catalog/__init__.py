"""Task registration, discovery, and resolution."""

from .resolver import installed_tasks, list_installed_task_definitions, resolve_task

__all__ = ["installed_tasks", "list_installed_task_definitions", "resolve_task"]
