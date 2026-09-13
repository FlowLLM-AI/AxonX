"""Description of an installed Task."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..enums import TaskType


class TaskInfo(BaseModel):
    """Describe an installed Task and its public configuration."""

    model_config = ConfigDict(frozen=True)

    name: str
    source: Literal["native", "plugin"]
    task_type: TaskType
    description: str
    config_schema: dict[str, Any]
    output_keys: tuple[str, ...]
