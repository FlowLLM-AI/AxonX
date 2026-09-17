"""Common contract for analysis tasks."""

from abc import ABC

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class BaseAnalysisInputParams(BaseInputParams):
    etl_task_id: str


class BaseAnalysisOutputParams(BaseOutputParams):
    metadata_file: str
    result_file: str
    rows: int


class BaseAnalysisTask(BaseTask, ABC):
    """Analyze a completed ETL task."""

    task_type = TaskType.ANALYSIS
    input_cls = BaseAnalysisInputParams
    output_cls = BaseAnalysisOutputParams
