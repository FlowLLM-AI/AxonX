"""Track step state and publish progress before matching metadata snapshots."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from ..models.identity import TaskState
from ..models.lifecycle import TaskMetadata, TaskStepStatus
from ..storage.logs import TaskJournal
from ..storage.workspace import EVENTS_FILE, PERSISTENT_DIR, write_task_metadata


class TaskProgress:
    """Own one execution's step state, progress throttling and ordered publication."""

    def __init__(self, directory: Path, status: TaskMetadata, *, previous_started_at: datetime | None = None) -> None:
        self.directory = directory
        self.status = status
        self.journal = TaskJournal(directory / EVENTS_FILE)
        self.runs = TaskJournal(directory / PERSISTENT_DIR / "runs.jsonl")
        self.previous_started_at = previous_started_at
        self._published_state: TaskState | None = None
        self.current: TaskStepStatus | None = None
        self._published: dict[tuple[str, str], float] = {}

    def publish(self, *steps: TaskStepStatus) -> None:
        """Write events first; terminal metadata includes every final step snapshot."""
        self.journal.append_snapshots(self.status.steps if self.status.state.is_terminal else steps)
        write_task_metadata(self.directory, self.status)
        if self.status.state != self._published_state:
            previous = self.previous_started_at if self.status.state == TaskState.RUNNING else None
            self.runs.append_run(self.status, previous_started_at=previous)
            self._published_state = self.status.state

    def report(self, percentage: float | None = None, *, name: str | None = None, **changes) -> None:
        step = self.current
        if step is None:
            raise RuntimeError("Progress can only be reported while a task step is running")
        if name is None:
            if changes or percentage is None or not 0 <= percentage <= 100:
                raise ValueError("percentage must be between 0 and 100")
            if step.percentage is not None and percentage < step.percentage:
                raise ValueError("percentage cannot move backwards")
            step.percentage = percentage
            step.updated_at = datetime.now(UTC)
            self.publish(step)
            return

        now = datetime.now(UTC)
        previous = next((s for s in self.status.steps if s.parent == step.name and s.name == name), None)
        values = previous.model_dump() if previous else {"name": name, "label": name, "parent": step.name}
        values.update(changes, name=name, parent=step.name, updated_at=now)
        if percentage is not None:
            values["percentage"] = percentage
        if values.get("state") == "running" and not values.get("started_at"):
            values["started_at"] = now
        terminal = values.get("state") in {"done", "failed", "missed", "skipped"}
        if terminal:
            values["finished_at"] = values.get("finished_at") or now
        updated = TaskStepStatus.model_validate(values)
        if previous is None:
            self.status.steps.append(updated)
        else:
            self.status.steps[self.status.steps.index(previous)] = updated

        transition = previous is None or (previous.state, previous.phase) != (updated.state, updated.phase)
        identity = (step.name, name)
        published_at = perf_counter()
        if transition or terminal or published_at - self._published.get(identity, 0) >= 1:
            self.publish(updated)
            self._published[identity] = published_at

    @contextmanager
    def step(self, name: str):
        """Record a step's outcome; retain failed steps until resource cleanup ends."""
        current = TaskStepStatus(name=name, state="running", started_at=datetime.now(UTC))
        self.current = current
        self.status.steps.append(current)
        self.publish(current)
        try:
            yield
        except BaseException as exc:
            current.state = "failed"
            current.error = f"{type(exc).__name__}: {exc}"
            raise
        else:
            current.state = "done"
            current.percentage = 100
        finally:
            current.finished_at = current.updated_at = datetime.now(UTC)
            self.publish(current)
            if current.state == "done":
                self.current = None
