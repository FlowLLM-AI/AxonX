"""Task categories, lifecycle states, names and dependency identities."""

from __future__ import annotations

import re
import secrets
import string
from collections.abc import Callable, Collection
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class TaskState(StrEnum):
    """The durable lifecycle state of a Task invocation."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self != TaskState.RUNNING


class TaskType(StrEnum):
    """Task producer types, also used in Task IDs and protocol headers."""

    BASE = "base"
    COMPOSITE = "composite"
    API = "api"
    ETL = "etl"
    ANALYSIS = "analysis"
    TRAIN = "train"
    PREDICT = "predict"
    INFERENCE = "inference"
    BACKTEST = "backtest"


class TaskCategory(StrEnum):
    DATA_UPDATE = "data_update"
    ONLINE_PREDICTION = "online_prediction"
    COMPARISON = "comparison"


TASK_ID_SEPARATOR = "#"
TASK_NAME_PATTERN = r"^[A-Za-z0-9-]{1,32}$"
GENERATED_TASK_NAME_TIME_FORMAT = "%Y%m%d%H"

_REG_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_TASK_NAME = re.compile(TASK_NAME_PATTERN)
_RANDOM_ALPHABET = string.ascii_letters + string.digits


def validate_task_name(name: str) -> str:
    """Validate the shared naming rule for inputs, IDs and sync filters."""
    if not isinstance(name, str) or not _TASK_NAME.fullmatch(name):
        raise ValueError("task_name must contain 1-32 letters, digits, or hyphens")
    return name


def generated_task_name(created_at: datetime) -> str:
    """Return a sortable anonymous Task name with an hour prefix."""
    suffix = "".join(secrets.choice(_RANDOM_ALPHABET) for _ in range(4))
    return f"{created_at.strftime(GENERATED_TASK_NAME_TIME_FORMAT)}{suffix}"


def task_type_from_id(task_id: str) -> TaskType:
    """Read the task category from a canonical task ID."""
    if not isinstance(task_id, str) or Path(task_id).name != task_id:
        raise ValueError(f"Invalid task ID: {task_id!r}")
    parts = task_id.split(TASK_ID_SEPARATOR)
    if len(parts) != 3 or not _REG_NAME.fullmatch(parts[1]) or not _TASK_NAME.fullmatch(parts[2]):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    try:
        return TaskType(parts[0])
    except ValueError:
        raise ValueError(f"Invalid task type in ID: {task_id!r}") from None


def parse_source_tasks(value: str) -> list[str]:
    """Parse task IDs separated by ASCII commas; reject malformed dependencies."""
    if not isinstance(value, str):
        raise ValueError("source_tasks must be a comma-separated string")
    if not value.strip():
        return []
    sources = [item.strip() for item in value.split(",")]
    for task_id in sources:
        task_type_from_id(task_id)
    if len(sources) != len(set(sources)):
        raise ValueError("source_tasks contains duplicate task IDs")
    return sources


def validate_registration_name(name: str) -> str:
    """Validate and return one Task catalog name."""
    if not isinstance(name, str) or not _REG_NAME.fullmatch(name):
        raise ValueError(f"Invalid Task registration name: {name!r}")
    return name


def _validate_selection(
    values: Collection[str] | None, validator: Callable[[str], object], field: str, label: str
) -> frozenset[str]:
    if values is not None and not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError(f"{field} must be a list of {label}")
    for value in values or ():
        validator(value)
    return frozenset(values or ())


def validate_task_names(values: Collection[str] | None) -> frozenset[str]:
    return _validate_selection(values, validate_task_name, "task_names", "task names")


def matches_task_name(task_id: str, task_names: frozenset[str]) -> bool:
    return not task_names or task_id.rsplit(TASK_ID_SEPARATOR, 1)[-1] in task_names


def validate_task_ids(values: Collection[str] | None) -> frozenset[str]:
    return _validate_selection(values, task_type_from_id, "task_ids", "Task IDs")
