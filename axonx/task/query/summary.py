"""Project task status snapshots into bounded list responses."""

from pydantic import BaseModel

from ..status import TaskStatus
from ..storage.workspace import TaskMetadata


class StepProgress(BaseModel):
    current: int
    total: int
    name: str
    percentage: float | None


class TaskSummary(TaskStatus):
    """Query projection only; never persisted beside the lifecycle record."""

    display_name: str
    is_online: bool
    is_replica: bool
    step_progress: StepProgress | None


def task_sort_key(metadata: TaskMetadata) -> tuple[float, str]:
    """Order lifecycle records consistently by creation time and Task ID."""
    return (
        (metadata.created_at.timestamp() if metadata.created_at is not None else float("-inf")),
        metadata.task_id,
    )


def summarize_status(status: TaskMetadata) -> TaskSummary:
    """Keep list metadata and one progress summary, without copying task outputs."""
    summary = {name: getattr(status, name) for name in TaskStatus.model_fields}
    summary["error"] = status.error[:1000]
    summary["display_name"] = str(status.input_params.get("task_name") or status.reg_name)[:256]
    summary["is_online"] = status.report_kind in {"online", "online_pipeline"}
    summary["is_replica"] = status.replica is not None
    summary["step_progress"] = None
    steps = [step for step in status.steps if step.parent is None]
    if steps:
        index = next(
            (i for i, step in enumerate(steps) if step.finished_at is None),
            len(steps) - 1,
        )
        step = steps[index]
        summary["step_progress"] = {
            "current": index + 1,
            "total": len(steps),
            "name": step.name[:256],
            "percentage": step.percentage,
        }
    return TaskSummary(**summary)
