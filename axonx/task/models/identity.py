"""Task producer types, lifecycle states, names and dependency identities."""

from __future__ import annotations

import re
import secrets
import string
from collections.abc import Callable, Collection
from datetime import datetime
from enum import StrEnum


class TaskState(StrEnum):
    """The durable lifecycle state of a Task invocation."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self != TaskState.RUNNING


class TaskType(StrEnum):
    """Task producer types, also used in Task IDs and protocol headers."""

    BASE = "base"
    API = "api"
    ETL = "etl"
    ANALYSIS = "analysis"
    TRAIN = "train"
    PREDICT = "predict"
    INFERENCE = "inference"
    PORTFOLIO = "portfolio"
    BACKTEST = "backtest"


TASK_ID_SEPARATOR = "#"

_REG_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_TASK_NAME = re.compile(r"^[A-Za-z0-9-]{1,32}$")
_RANDOM_ALPHABET = string.ascii_letters + string.digits
_GENERATED_NAME = re.compile(r"^[0-9]{10}[A-Za-z0-9]{4}$")


def validate_task_name(name: str) -> str:
    """Validate the shared naming rule for inputs, IDs and sync filters."""
    if not isinstance(name, str) or not _TASK_NAME.fullmatch(name):
        raise ValueError("task_name must contain 1-32 letters, digits, or hyphens")
    return name


def generated_task_name(created_at: datetime) -> str:
    """Return a sortable anonymous Task name with an hour prefix."""
    suffix = "".join(secrets.choice(_RANDOM_ALPHABET) for _ in range(4))
    return f"{created_at:%Y%m%d%H}{suffix}"


def is_generated_task_name(name: str) -> bool:
    """Recognize the reserved hour-and-random-suffix namespace, including inherited names."""
    if not _GENERATED_NAME.fullmatch(name):
        return False
    try:
        datetime.strptime(name[:10], "%Y%m%d%H")
    except ValueError:
        return False
    return True


def task_type_from_id(task_id: str) -> TaskType:
    """Read the producer type from a canonical Task ID."""
    if not isinstance(task_id, str):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    parts = task_id.split(TASK_ID_SEPARATOR)
    if len(parts) != 3 or not _REG_NAME.fullmatch(parts[1]) or not _TASK_NAME.fullmatch(parts[2]):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    try:
        return TaskType(parts[0])
    except ValueError:
        raise ValueError(f"Invalid task type in ID: {task_id!r}") from None


def validate_upstream_task_ids(task_ids: list[str]) -> list[str]:
    """Validate an ordered list of distinct upstream Task IDs."""
    if not isinstance(task_ids, list):
        raise ValueError("upstream_task_ids must be a list of Task IDs")
    for task_id in task_ids:
        task_type_from_id(task_id)
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("upstream_task_ids contains duplicate task IDs")
    return task_ids


def validate_registration_name(name: str) -> str:
    """Validate and return one Task catalog name."""
    if not isinstance(name, str) or not _REG_NAME.fullmatch(name):
        raise ValueError(f"Invalid Task registration name: {name!r}")
    return name


def _validate_selection(
    values: Collection[str] | None, validator: Callable[[str], object], message: str
) -> frozenset[str]:
    if values is not None and not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError(message)
    for value in values or ():
        validator(value)
    return frozenset(values or ())


def validate_task_names(values: Collection[str] | None) -> frozenset[str]:
    return _validate_selection(values, validate_task_name, "task_names must be a list of task names")


def validate_task_ids(values: Collection[str] | None) -> frozenset[str]:
    return _validate_selection(values, task_type_from_id, "task_ids must be a list of Task IDs")
