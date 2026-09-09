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
