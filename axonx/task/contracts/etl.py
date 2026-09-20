"""Standard contract for ETL Tasks."""

from abc import ABC
from pathlib import Path

from pydantic import Field

from ...enums import TaskType
from ..core import BaseInputParams, BaseOutputParams, BaseTask


class BaseETLInputParams(BaseInputParams):
    input_dir: Path = Field(
        description="Directory containing the source data to transform."
    )


class BaseETLOutputParams(BaseOutputParams):
    output_file: str
    rows: int
    date_range: dict[str, str]
    feature_columns: list[str] = Field(default_factory=list)
    label_columns: list[str] = Field(default_factory=list)


class BaseETLTask(BaseTask, ABC):
    """Transform source data into a dataset for downstream tasks.

    The output records the saved file, date range, and available columns.
    """

    task_type = TaskType.ETL
    input_cls = BaseETLInputParams
    output_cls = BaseETLOutputParams
