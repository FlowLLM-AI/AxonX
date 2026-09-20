"""Canonical Task identity parsing and construction."""

from __future__ import annotations

import re
import secrets
import string
from datetime import datetime
from pathlib import Path

from ...constants import (
    GENERATED_TASK_NAME_TIME_FORMAT,
    TASK_ID_SEPARATOR,
    TASK_NAME_PATTERN,
)
from ...enums import TaskType

_REG_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_TASK_NAME = re.compile(TASK_NAME_PATTERN)
_RANDOM_ALPHABET = string.ascii_letters + string.digits


def generated_task_name(created_at: datetime) -> str:
    """Return a sortable anonymous Task name with an hour prefix."""
    suffix = "".join(secrets.choice(_RANDOM_ALPHABET) for _ in range(4))
    return f"{created_at.strftime(GENERATED_TASK_NAME_TIME_FORMAT)}{suffix}"


def task_type_from_id(task_id: str) -> TaskType:
    """Read the task category from a canonical task ID."""
    if not isinstance(task_id, str) or Path(task_id).name != task_id:
        raise ValueError(f"Invalid task ID: {task_id!r}")
    parts = task_id.split(TASK_ID_SEPARATOR)
    if (
        len(parts) != 3
        or not _REG_NAME.fullmatch(parts[1])
        or not _TASK_NAME.fullmatch(parts[2])
    ):
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
