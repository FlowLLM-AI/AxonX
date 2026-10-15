"""Standard contract for analysis Tasks."""

from abc import ABC

from pydantic import Field

from ...enums import TaskType
from ..core import BaseInputParams, BaseOutputParams, BaseTask


class BaseAnalysisOutputParams(BaseOutputParams):
    rows: int
    scores: dict[str, dict[str, float]] = Field(default_factory=dict)


class BaseAnalysisTask(BaseTask, ABC):
    """Analyze a completed ETL dataset and save the results.

    The output includes a result file, its row count, and optional scores.
    """

    task_type = TaskType.ANALYSIS
    input_cls = BaseInputParams
    output_cls = BaseAnalysisOutputParams
