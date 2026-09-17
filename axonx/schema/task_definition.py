"""Definition of an installed Task."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..enums import TaskType


class TaskDefinition(BaseModel):
    """Describe an installed Task and its input and output schemas."""

    model_config = ConfigDict(frozen=True)

    name: str
    source: Literal["native", "plugin"]
    plugin: str | None = None
    task_type: TaskType
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
