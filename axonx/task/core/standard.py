"""Standard research Task contracts and incremental prediction comparisons."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.identity import TaskType
from ..models.params import (
    BaseAnalysisOutputParams,
    BaseBacktestOutputParams,
    BaseETLInputParams,
    BaseETLOutputParams,
    BasePredictionCompareInputParams,
    BasePredictionCompareOutputParams,
    BasePredictOutputParams,
    BaseTrainOutputParams,
)
from ..models.reports import PredictionComparison
from .task import BaseTask


class BaseAnalysisTask(BaseTask, ABC):
    """Analyze a completed ETL dataset and save the results.

    The output includes a result file, its row count, and optional scores.
    """

    task_type = TaskType.ANALYSIS
    output_cls = BaseAnalysisOutputParams


class BaseETLTask(BaseTask, ABC):
    """Transform source data into a dataset for downstream tasks.

    The output records the saved file, date range, and available columns.
    """

    task_type = TaskType.ETL
    input_cls = BaseETLInputParams
    output_cls = BaseETLOutputParams


class BaseBacktestTask(BaseTask, ABC):
    """Evaluate predictions and publish standard daily and summary artifacts."""

    task_type = TaskType.BACKTEST
    output_cls = BaseBacktestOutputParams


class BasePredictTask(BaseTask, ABC):
    """Generate predictions from a completed training task.

    The saved predictions include dates and values for downstream evaluation.
    """

    task_type = TaskType.PREDICT
    output_cls = BasePredictOutputParams


class BaseTrainTask(BaseTask, ABC):
    """Train a model using a completed ETL dataset.

    The result includes the saved model, training metrics, and optional curves.
    """

    task_type = TaskType.TRAIN
    output_cls = BaseTrainOutputParams


class BasePredictionCompareTask(BaseAnalysisTask):
    """Persist each comparison, retaining per-key errors while continuing the report."""

    report_kind = "online"
    input_cls = BasePredictionCompareInputParams
    output_cls = BasePredictionCompareOutputParams
    comparisons: list[PredictionComparison]

    @abstractmethod
    def compare(self, key: str) -> PredictionComparison:
        """Compare one key; missing inputs are a report outcome."""

    def build_task_steps(self):
        yield self.compare_predictions

    def compare_predictions(self) -> None:
        self.comparisons = []
        for key in self.input_params.comparison_keys:
            try:
                result = self.compare(key)
                if result.key != key:
                    raise ValueError("Comparison result key does not match request")
            except Exception as exc:
                result = PredictionComparison(key=key, status="error", reason=f"{type(exc).__name__}: {exc}")
            self.comparisons.append(result)
            self.metadata.output_params["comparisons"] = [item.model_dump(mode="json") for item in self.comparisons]
            self.persist_metadata()

    def build_output_params(self) -> BasePredictionCompareOutputParams:
        return self.output_cls(comparisons=self.comparisons)
