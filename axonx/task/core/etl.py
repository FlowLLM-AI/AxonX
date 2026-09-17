"""Common contract for ETL tasks."""

from abc import ABC
from pathlib import Path

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class BaseETLInputParams(BaseInputParams):
    input_dir: Path


class BaseETLOutputParams(BaseOutputParams):
    metadata_file: str
    output_file: str
    rows: int
    date_range: dict[str, str]


class BaseETLTask(BaseTask, ABC):
    """Build a dataset from a source directory."""

    task_type = TaskType.ETL
    input_cls = BaseETLInputParams
    output_cls = BaseETLOutputParams
