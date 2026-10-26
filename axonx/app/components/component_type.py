"""Built-in application component types."""

from __future__ import annotations

from enum import StrEnum


class ComponentType(StrEnum):
    """Enumerate built-in component categories."""

    BASE = "base"
    JOB = "job"
    STEP = "step"
    TASK_INDEX = "task_index"
    SERVICE = "service"
    AGENT = "agent"
    SYNC = "sync"
    PROXY = "proxy"
    UPDATER = "updater"
    CRON = "cron"
