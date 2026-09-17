"""Common contract for prediction tasks."""

from abc import ABC

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class BasePredictInputParams(BaseInputParams):
    train_task_id: str


class BasePredictOutputParams(BaseOutputParams):
    metadata_file: str
    predictions_file: str
    rows: int
    date_range: dict[str, str]


class BasePredictTask(BaseTask, ABC):
    """Predict from a completed training task."""

    task_type = TaskType.PREDICT
    input_cls = BasePredictInputParams
    output_cls = BasePredictOutputParams
