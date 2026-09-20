"""Canonical Task identity parsing and construction."""

from __future__ import annotations

import re
from pathlib import Path

from ...constants import TASK_ID_SEPARATOR, TASK_NAME_PATTERN
from ...enums import TaskType

_REG_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_TASK_NAME = re.compile(TASK_NAME_PATTERN)
_TIMESTAMP = re.compile(r"^[0-9]{10}(?:[0-9]{4}(?:[0-9]{6})?)?$")


def task_type_from_id(task_id: str) -> TaskType:
    """Read the task category from a canonical task ID."""
    if not isinstance(task_id, str) or Path(task_id).name != task_id:
        raise ValueError(f"Invalid task ID: {task_id!r}")
    parts = task_id.split(TASK_ID_SEPARATOR)
    if len(parts) not in (3, 4) or not _REG_NAME.fullmatch(parts[1]) or not _TASK_NAME.fullmatch(parts[2]):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    if len(parts) == 4 and not _TIMESTAMP.fullmatch(parts[3]):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    try:
        return TaskType(parts[0])
    except ValueError:
        raise ValueError(f"Invalid task type in ID: {task_id!r}") from None


def validate_registration_name(name: str) -> str:
    """Validate and return one Task catalog name."""
    if not isinstance(name, str) or not _REG_NAME.fullmatch(name):
        raise ValueError(f"Invalid Task registration name: {name!r}")
    return name
