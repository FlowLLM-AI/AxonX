"""Values returned when a Task is accepted for execution."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskHandle:
    task_id: str
    run_id: str
    task: str
