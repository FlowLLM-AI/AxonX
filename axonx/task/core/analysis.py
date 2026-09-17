"""Common contract for analysis tasks."""

from abc import ABC
from pydantic import Field

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class BaseAnalysisInputParams(BaseInputParams):
    pass


class BaseAnalysisOutputParams(BaseOutputParams):
    result_file: str
    rows: int
    scores: dict[str, dict[str, float]] = Field(default_factory=dict)


class BaseAnalysisTask(BaseTask, ABC):
    """Analyze a completed ETL task."""

    task_type = TaskType.ANALYSIS
    input_cls = BaseAnalysisInputParams
    output_cls = BaseAnalysisOutputParams
