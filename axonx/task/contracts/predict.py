"""Standard contract for prediction Tasks."""

from abc import ABC
from typing import Any

from pydantic import Field, model_validator

from ...enums import TaskType
from ..protocol import PredictionProtocol
from ..core import BaseInputParams, BaseOutputParams, BaseTask


class BasePredictInputParams(BaseInputParams):
    pass


class BasePredictOutputParams(BaseOutputParams):
    """Describe the prediction artifact consumed by downstream tasks."""

    predictions_file: str
    score_columns: dict[str, str] = Field(min_length=1, description="Model member IDs mapped to raw score columns.")
    rows: int
    date_range: dict[str, str]
    output_columns: list[str] = Field(default_factory=list)
    protocol: dict[str, Any]
    statistics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_prediction_protocol(self):
        protocol = PredictionProtocol.model_validate(self.protocol)
        if protocol.task_type != TaskType.PREDICT or protocol.score_columns != self.score_columns:
            raise ValueError("Prediction output differs from its protocol")
        return self


class BasePredictTask(BaseTask, ABC):
    """Generate predictions from a completed training task.

    The saved predictions include dates and values for downstream evaluation.
    """

    task_type = TaskType.PREDICT
    input_cls = BasePredictInputParams
    output_cls = BasePredictOutputParams
