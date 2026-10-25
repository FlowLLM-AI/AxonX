"""Lazy authoring exports, independent of metadata-reader import order."""

from typing import TYPE_CHECKING

from ...common.imports import lazy_export

if TYPE_CHECKING:
    from .context import TaskContext
    from .identity import (
        parse_source_tasks,
        task_type_from_id,
        validate_registration_name,
    )
    from .params import BaseInputParams, BaseOutputParams
    from .task import BaseTask, TaskStep

_EXPORTS = {
    "BaseInputParams": ("params", "BaseInputParams"),
    "BaseOutputParams": ("params", "BaseOutputParams"),
    "BaseTask": ("task", "BaseTask"),
    "TaskStep": ("task", "TaskStep"),
    "TaskContext": ("context", "TaskContext"),
    "parse_source_tasks": ("identity", "parse_source_tasks"),
    "task_type_from_id": ("identity", "task_type_from_id"),
    "validate_registration_name": ("identity", "validate_registration_name"),
}
__all__ = [
    "BaseInputParams",
    "BaseOutputParams",
    "BaseTask",
    "TaskStep",
    "TaskContext",
    "parse_source_tasks",
    "task_type_from_id",
    "validate_registration_name",
]


def __getattr__(name: str):
    return lazy_export(globals(), name, _EXPORTS)
