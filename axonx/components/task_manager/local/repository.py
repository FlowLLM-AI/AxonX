"""Durable storage for local Task status snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from ....schema import TaskStatus
from ....utils.fs import atomic_write_json


@dataclass(frozen=True)
class StatusLoadResult:
    """Statuses loaded from one compatible status file."""

    statuses: dict[str, TaskStatus]
    should_save: bool
    foreign_workspace: str | None = None


class TaskStatusRepository:
    """Load and atomically save the Task manager status file."""

    def __init__(self, workspace: Path, version: int) -> None:
        self.workspace = workspace.resolve()
        self.version = version

    @property
    def directory(self) -> Path:
        """Return the state directory, creating it when first used."""
        directory = self.workspace / "task_manager"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def path(self) -> Path:
        """Return the status file path."""
        return self.directory / "status.json"

    def load(self) -> StatusLoadResult | None:
        """Load a compatible snapshot or return ``None`` when none exists."""
        if not self.path.is_file():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != self.version:
            return StatusLoadResult({}, should_save=False)

        saved_workspace = data.get("workspace")
        if saved_workspace is not None and Path(saved_workspace).expanduser().resolve() != self.workspace:
            return StatusLoadResult({}, should_save=True, foreign_workspace=saved_workspace)

        statuses = (TaskStatus.model_validate(value) for value in data.get("tasks", []))
        return StatusLoadResult(
            {status.task_id: status for status in statuses},
            should_save=True,
        )

    def save(self, statuses: Iterable[TaskStatus]) -> None:
        """Persist complete Task snapshots using atomic JSON replacement."""
        atomic_write_json(
            self.path,
            {
                "version": self.version,
                "workspace": str(self.workspace),
                "tasks": [status.model_dump(mode="json") for status in statuses],
            },
        )
