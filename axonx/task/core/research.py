"""Standard research Task contracts and incremental prediction comparisons."""

from __future__ import annotations

import calendar
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime, timedelta

from ..models.base import normalize_yyyymmdd
from ..models.identity import TaskType
from ..models.params import (
    BaseAnalysisOutputParams,
    BaseBacktestOutputParams,
    BaseETLInputParams,
    BaseETLOutputParams,
    BasePortfolioOutputParams,
    BasePredictionCompareInputParams,
    BasePredictionCompareOutputParams,
    BasePredictOutputParams,
    BaseTrainOutputParams,
)
from ..models.reports import PredictionComparison
from .base import BaseTask


def date_windows(start: int, end: int, months: int) -> Iterator[tuple[int, int]]:
    """Yield half-open calendar windows through an inclusive end date."""
    first = datetime.strptime(normalize_yyyymmdd(start), "%Y%m%d").date()
    stop = datetime.strptime(normalize_yyyymmdd(end), "%Y%m%d").date() + timedelta(days=1)
    if start > end or months < 0:
        raise ValueError("Require start <= end and months >= 0")
    current, offset = first, months
    while current < stop:
        if months:
            year, month = divmod(first.year * 12 + first.month - 1 + offset, 12)
            month += 1
            following = first.replace(year=year, month=month, day=min(first.day, calendar.monthrange(year, month)[1]))
            following = min(following, stop)
        else:
            following = stop
        yield int(current.strftime("%Y%m%d")), int(following.strftime("%Y%m%d"))
        current, offset = following, offset + months


class BaseETLTask(BaseTask, ABC):
    """Transform source data into a dataset with date and column metadata."""

    task_type = TaskType.ETL
    input_cls = BaseETLInputParams
    output_cls = BaseETLOutputParams


class BaseAnalysisTask(BaseTask, ABC):
    """Analyze a completed dataset and publish row counts and scores."""

    task_type = TaskType.ANALYSIS
    output_cls = BaseAnalysisOutputParams


class BaseTrainTask(BaseTask, ABC):
    """Train a model and publish its artifacts, metrics and learning curves."""

    task_type = TaskType.TRAIN
    output_cls = BaseTrainOutputParams


class BasePredictTask(BaseTask, ABC):
    """Generate predictions from a trained model for downstream evaluation."""

    task_type = TaskType.PREDICT
    output_cls = BasePredictOutputParams


class BasePortfolioTask(BaseTask, ABC):
    """Construct reusable portfolio targets and declare their decision rules."""

    task_type = TaskType.PORTFOLIO
    output_cls = BasePortfolioOutputParams


class BaseBacktestTask(BaseTask, ABC):
    """Execute portfolio plans and publish standard daily and summary artifacts."""

    task_type = TaskType.BACKTEST
    output_cls = BaseBacktestOutputParams


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
                self.logger.exception("Prediction comparison failed key={}", key)
                result = PredictionComparison(key=key, status="error", reason=f"{type(exc).__name__}: {exc}")
            self.comparisons.append(result)
            self.publish_output()

    def build_output_params(self) -> BasePredictionCompareOutputParams:
        return self.output_cls(comparisons=self.comparisons)

    def exit_code(self, output: dict) -> int:
        return super().exit_code(output) or int(any(item["status"] == "error" for item in output["comparisons"]))
