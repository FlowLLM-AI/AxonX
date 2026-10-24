"""Application component categories."""

from enum import StrEnum


class ComponentEnum(StrEnum):
    """Enumerate built-in component categories."""

    BASE = "base"
    JOB = "job"
    STEP = "step"
    TASK_REPOSITORY = "task_repository"
    SERVICE = "service"
    CLIENT = "client"
    AGENT = "agent"
    SYNC = "sync"
    PROXY = "proxy"
    UPDATER = "updater"
