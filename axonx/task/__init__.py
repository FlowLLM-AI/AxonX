"""Lazy Task authoring API; metadata readers do not load executable Tasks."""

from typing import TYPE_CHECKING

from ..common.imports import lazy_export

if TYPE_CHECKING:
    from .core.composite import (
        BaseCompositeTask,
        ChildTaskError,
        ChildTaskResult,
    )
    from .core.params import BaseInputParams, BaseOutputParams
    from .core.task import BaseTask, TaskStep
    from .schemas.lifecycle import TaskMetadata
    from .schemas.progress import TaskStepStatus

_EXPORTS = {
    "BaseInputParams": ("core.params", "BaseInputParams"),
    "BaseOutputParams": ("core.params", "BaseOutputParams"),
    "BaseTask": ("core.task", "BaseTask"),
    "TaskStep": ("core.task", "TaskStep"),
    "BaseCompositeTask": ("core.composite", "BaseCompositeTask"),
    "ChildTaskError": ("core.composite", "ChildTaskError"),
    "ChildTaskResult": ("core.composite", "ChildTaskResult"),
    "TaskMetadata": ("schemas.lifecycle", "TaskMetadata"),
    "TaskStepStatus": ("schemas.progress", "TaskStepStatus"),
}
__all__ = [
    "BaseInputParams",
    "BaseOutputParams",
    "BaseTask",
    "TaskStep",
    "BaseCompositeTask",
    "ChildTaskError",
    "ChildTaskResult",
    "TaskMetadata",
    "TaskStepStatus",
]


def __getattr__(name: str):
    return lazy_export(globals(), name, _EXPORTS)
