"""Progress for executable Task steps and their concurrent substeps."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from datetime import datetime

from pydantic import TypeAdapter, AwareDatetime, BaseModel, ConfigDict, Field

from ...common.logs import LogEvent


class TaskStepStatus(BaseModel):
    """One step snapshot, shared by persistence and progress events."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    label: str = ""
    parent: str | None = None
    percentage: float | None = Field(default=None, ge=0, le=100)
    group: str = ""
    state: Literal["pending", "waiting", "running", "done", "failed", "missed", "skipped"] = "pending"
    phase: str = ""
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    unit: str = ""
    scheduled_at: AwareDatetime | None = None
    deadline: AwareDatetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, str] = Field(default_factory=dict)
    error: str = ""


def settle_steps(steps: list[TaskStepStatus], *, failed: bool, error: str, now: datetime) -> None:
    """Settle unfinished progress after all owned producers stop."""
    for step in steps:
        if step.state in {"pending", "waiting", "running"}:
            step.state = "failed" if failed else "skipped"
            step.error = error
            step.finished_at = step.updated_at = now


class ProgressEvent(TaskStepStatus):
    kind: Literal["progress"] = "progress"

    @classmethod
    def from_status(cls, status: Any) -> ProgressEvent:
        return cls.model_validate(status, from_attributes=True)


type TaskEvent = Annotated[ProgressEvent | LogEvent, Field(discriminator="kind")]
TASK_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)
