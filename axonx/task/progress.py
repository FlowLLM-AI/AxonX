"""Domain execution and shared operations."""

from __future__ import annotations

from datetime import datetime

from .models.lifecycle import TaskStepStatus


def settle_steps(steps: list[TaskStepStatus], *, failed: bool, error: str, now: datetime) -> None:
    """Settle unfinished progress after all owned producers stop."""
    for step in steps:
        if step.state in {"pending", "waiting", "running"}:
            step.state = "failed" if failed else "skipped"
            step.error = error
            step.finished_at = step.updated_at = now
