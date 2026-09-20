"""Persist the completed Task's typed metadata."""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, SerializeAsAny

from ...enums import TaskType
from ...utils.fs import atomic_write_json
from ..core.params import BaseInputParams, BaseOutputParams

if TYPE_CHECKING:
    from ..core.task import BaseTask


class TaskMetadata(BaseModel):
    """Common persisted envelope around task specific input and output."""

    task_id: str
    reg_name: str
    created_at: datetime
    task_type: TaskType
    input_params: SerializeAsAny[BaseInputParams]
    output_params: SerializeAsAny[BaseOutputParams]


def write_task_metadata(task: BaseTask) -> None:
    metadata = TaskMetadata(
        task_id=task.task_id,
        reg_name=task.reg_name,
        created_at=task.created_at,
        task_type=task.task_type,
        input_params=task.input_params,
        output_params=task.output_params,
    )

    def finite(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: finite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [finite(item) for item in value]
        return value

    atomic_write_json(task.metadata_path, finite(metadata.model_dump(mode="json", by_alias=True)))
