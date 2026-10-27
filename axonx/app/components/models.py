"""Component categories, dependency declarations and value validation."""

from __future__ import annotations

from dataclasses import dataclass
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


def component_type_name(value: str) -> str:
    """Normalize a component enum or non-empty string to its string name."""
    if not isinstance(value, str) or not value:
        raise ValueError("Component type must be a non-empty string")
    return str(value)


@dataclass(frozen=True, slots=True)
class DependencySpec[ComponentT]:
    """A component attribute that must be injected before startup."""

    attribute: str
    component_type: str
    name: str
    required: bool
    expected_type: type[ComponentT]
