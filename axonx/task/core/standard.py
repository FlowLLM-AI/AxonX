"""Domain execution and shared operations."""

from __future__ import annotations

from abc import ABC

from .task import BaseTask
from ..task_enums import TaskType
from ..models.params import (
    BaseAnalysisOutputParams,
    BaseBacktestOutputParams,
    BaseETLInputParams,
    BaseETLOutputParams,
    BaseInputParams,
    BasePredictOutputParams,
    BaseTrainOutputParams,
)


class BaseAnalysisTask(BaseTask, ABC):
    """Analyze a completed ETL dataset and save the results.

    The output includes a result file, its row count, and optional scores.
    """

    task_type = TaskType.ANALYSIS
    input_cls = BaseInputParams
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
    input_cls = BaseInputParams
    output_cls = BaseBacktestOutputParams


class BasePredictTask(BaseTask, ABC):
    """Generate predictions from a completed training task.

    The saved predictions include dates and values for downstream evaluation.
    """

    task_type = TaskType.PREDICT
    input_cls = BaseInputParams
    output_cls = BasePredictOutputParams


class BaseTrainTask(BaseTask, ABC):
    """Train a model using a completed ETL dataset.

    The result includes the saved model, training metrics, and optional curves.
    """

    task_type = TaskType.TRAIN
    input_cls = BaseInputParams
    output_cls = BaseTrainOutputParams
