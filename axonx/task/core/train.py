"""Common contract for training tasks."""

from abc import ABC

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class BaseTrainInputParams(BaseInputParams):
    etl_task_id: str


class BaseTrainOutputParams(BaseOutputParams):
    metadata_file: str
    model_file: str
    train_rows: int


class BaseTrainTask(BaseTask, ABC):
    """Train a model from a completed ETL task."""

    task_type = TaskType.TRAIN
    input_cls = BaseTrainInputParams
    output_cls = BaseTrainOutputParams
