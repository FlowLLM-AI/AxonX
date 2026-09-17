"""Common contract for training tasks."""

from abc import ABC
from typing import Any

from pydantic import Field

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams
from .artifact_task import BaseArtifactTask


class BaseTrainInputParams(BaseInputParams):
    pass


class BaseTrainOutputParams(BaseOutputParams):
    model_file: str
    train_rows: int
    model_name: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


class BaseTrainTask(BaseArtifactTask, ABC):
    """Train a model from a completed ETL task."""

    task_type = TaskType.TRAIN
    input_cls = BaseTrainInputParams
    output_cls = BaseTrainOutputParams
