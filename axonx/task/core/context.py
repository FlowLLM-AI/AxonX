"""Immutable identity and services attached to one Task invocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models.lifecycle import TaskSource


@dataclass(frozen=True)
class TaskContext:
    """Runtime-owned values a Task may read but must not mutate."""

    workspace_path: Path
    registration_name: str
    task_id: str
    created_at: datetime
    logger: Any
    source: TaskSource
    parent_task_id: str | None = None
    execution_target: str | None = None
