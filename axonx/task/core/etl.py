"""Common contract for ETL tasks."""

from abc import ABC
from pathlib import Path
from pydantic import Field

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams
from .artifact_task import BaseArtifactTask


class BaseETLInputParams(BaseInputParams):
    input_dir: Path


class BaseETLOutputParams(BaseOutputParams):
    output_file: str
    rows: int
    date_range: dict[str, str]
    feature_columns: list[str] = Field(default_factory=list)
    label_columns: list[str] = Field(default_factory=list)


class BaseETLTask(BaseArtifactTask, ABC):
    """Build a dataset from a source directory."""

    task_type = TaskType.ETL
    input_cls = BaseETLInputParams
    output_cls = BaseETLOutputParams
