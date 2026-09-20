"""Standard contract for prediction Tasks."""

from abc import ABC
from typing import Any

from pydantic import Field

from ...enums import TaskType
from ..core import BaseInputParams, BaseOutputParams, BaseTask


class BasePredictInputParams(BaseInputParams):
    pass


class BasePredictOutputParams(BaseOutputParams):
    """Describe the prediction artifact consumed by downstream tasks."""

    predictions_file: str
    rows: int
    date_range: dict[str, str]
    output_columns: list[str] = Field(default_factory=list)
    protocol: dict[str, Any] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)


class BasePredictTask(BaseTask, ABC):
    """Generate predictions from a completed training task.

    The saved predictions include dates and values for downstream evaluation.
    """

    task_type = TaskType.PREDICT
    input_cls = BasePredictInputParams
    output_cls = BasePredictOutputParams
