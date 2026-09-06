"""Stable enumerations and component type normalization helpers."""

from .component_enum import ComponentEnum
from .task_state import TaskState

ComponentType = str | ComponentEnum

__all__ = [
    "ComponentEnum",
    "ComponentType",
    "TaskState",
    "component_type_name",
]


def component_type_name(value: ComponentType) -> str:
    """Normalize a component enum or non-empty string to its string name."""
    if not isinstance(value, str) or not value:
        raise ValueError("Component type must be a non-empty string")
    return str(value)
