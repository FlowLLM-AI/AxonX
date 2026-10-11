"""Project task status snapshots into bounded list responses."""

from ..storage.workspace import TaskStatus


def summarize_status(status: TaskStatus) -> dict:
    """Keep list metadata and one progress summary, without copying task outputs."""
    summary = {
        name: getattr(status, name)
        for name in (
            "task_id",
            "run_id",
            "task_type",
            "task_name",
            "state",
            "pid",
            "created_at",
            "started_at",
            "finished_at",
            "exit_code",
            "log_path",
        )
    }
    summary["error"] = status.error[:1000]
    summary["display_name"] = str(status.config.get("task_name") or status.task_name)[:256]
    summary["is_online"] = status.task_type.value in {"api", "inference"} or (
        status.task_type.value == "analysis"
        and (
            isinstance(status.result.get("comparisons"), list) or isinstance(status.config.get("comparison_keys"), list)
        )
    )
    summary["step_progress"] = None
    if status.steps:
        index = next((i for i, step in enumerate(status.steps) if step.finished_at is None), len(status.steps) - 1)
        step = status.steps[index]
        summary["step_progress"] = {
            "current": index + 1,
            "total": len(status.steps),
            "name": step.name[:256],
            "percentage": step.percentage,
        }
    return summary
