"""Common contract for prediction tasks."""

from abc import ABC
from pydantic import Field

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams
from .artifact_task import BaseArtifactTask


class BasePredictInputParams(BaseInputParams):
    pass


class BasePredictOutputParams(BaseOutputParams):
    predictions_file: str
    rows: int
    date_range: dict[str, str]
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)


class BasePredictTask(BaseArtifactTask, ABC):
    """Predict from a completed training task."""

    task_type = TaskType.PREDICT
    input_cls = BasePredictInputParams
    output_cls = BasePredictOutputParams
