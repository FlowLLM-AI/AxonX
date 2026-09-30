"""Task registration, discovery, and resolution."""

from .resolver import (
    get_task_definition,
    installed_tasks,
    list_installed_task_definitions,
    resolve_task,
)

__all__ = [
    "get_task_definition",
    "installed_tasks",
    "list_installed_task_definitions",
    "resolve_task",
]
