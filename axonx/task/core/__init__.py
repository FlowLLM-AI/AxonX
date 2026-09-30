"""Stable authoring API shared by built-in and plugin Tasks."""

from .context import TaskContext
from .identity import parse_source_tasks, task_type_from_id, validate_registration_name
from .params import BaseInputParams, BaseOutputParams
from .task import BaseTask, TaskStep

__all__ = [
    "BaseInputParams",
    "BaseOutputParams",
    "BaseTask",
    "TaskContext",
    "TaskStep",
    "parse_source_tasks",
    "task_type_from_id",
    "validate_registration_name",
]
