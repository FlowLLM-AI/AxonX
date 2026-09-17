"""Common contract for prediction tasks."""

from abc import ABC
from typing import Any
from pydantic import Field

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams
from .artifact_task import BaseArtifactTask


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


class BasePredictTask(BaseArtifactTask, ABC):
    """Predict from a completed training task."""

    task_type = TaskType.PREDICT
    input_cls = BasePredictInputParams
    output_cls = BasePredictOutputParams
