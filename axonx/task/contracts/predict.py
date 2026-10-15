"""Standard contract for prediction Tasks."""

from abc import ABC
from typing import Any

from pydantic import Field, model_validator

from ...enums import TaskType
from ..core import BaseInputParams, BaseOutputParams, BaseTask
from ..protocol import PredictionProtocol


class BasePredictOutputParams(BaseOutputParams):
    """Describe the prediction artifact consumed by downstream tasks."""

    rows: int
    date_range: dict[str, str]
    output_columns: list[str] = Field(default_factory=list)
    protocol: dict[str, Any]
    statistics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_prediction_protocol(self):
        protocol = PredictionProtocol.model_validate(self.protocol)
        if protocol.task_type != TaskType.PREDICT:
            raise ValueError("Prediction output differs from its protocol")
        return self


class BasePredictTask(BaseTask, ABC):
    """Generate predictions from a completed training task.

    The saved predictions include dates and values for downstream evaluation.
    """

    task_type = TaskType.PREDICT
    input_cls = BaseInputParams
    output_cls = BasePredictOutputParams
