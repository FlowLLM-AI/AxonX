"""Component category names shared by configuration and registries."""

from enum import StrEnum


class ComponentEnum(StrEnum):
    """Enumerate built-in component categories."""

    BASE = "base"
    JOB = "job"
    STEP = "step"
    TASK = "task"
    TASK_MANAGER = "task_manager"
    SERVICE = "service"
    CLIENT = "client"
    MACHINE = "machine"
    PLUGIN = "plugin"
    PROXY = "proxy"


ComponentType = str | ComponentEnum


def component_type_name(value: ComponentType) -> str:
    """Normalize a component enum or non-empty string to its string name."""
    if not isinstance(value, str) or not value:
        raise ValueError("Component type must be a non-empty string")
    return str(value)
