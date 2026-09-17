"""Common contract for training tasks."""

from abc import ABC
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams
from .artifact_task import BaseArtifactTask


class BaseTrainInputParams(BaseInputParams):
    pass


class TrainingCurve(BaseModel):
    """Aligned x-axis points and named training metric series."""

    x: list[str] = Field(default_factory=list)
    y: dict[str, list[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_series_lengths(self):
        if any(len(values) != len(self.x) for values in self.y.values()):
            raise ValueError("Every training curve series must match the x-axis length")
        return self


class BaseTrainOutputParams(BaseOutputParams):
    model_file: str
    train_rows: int
    model_name: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    training_curve: TrainingCurve = Field(default_factory=TrainingCurve)


class BaseTrainTask(BaseArtifactTask, ABC):
    """Train a model from a completed ETL task."""

    task_type = TaskType.TRAIN
    input_cls = BaseTrainInputParams
    output_cls = BaseTrainOutputParams
