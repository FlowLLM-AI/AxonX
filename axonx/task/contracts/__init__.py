"""Optional standard contracts for common data and model Task capabilities."""

from .analysis import (
    BaseAnalysisInputParams,
    BaseAnalysisOutputParams,
    BaseAnalysisTask,
)
from .backtest import (
    BacktestBenchmark,
    BacktestDimensions,
    BaseBacktestInputParams,
    BaseBacktestOutputParams,
    BaseBacktestTask,
)
from .etl import BaseETLInputParams, BaseETLOutputParams, BaseETLTask
from .predict import BasePredictInputParams, BasePredictOutputParams, BasePredictTask
from .submission import TaskHandle
from .train import (
    BaseTrainInputParams,
    BaseTrainOutputParams,
    BaseTrainTask,
    TrainingCurve,
)

__all__ = [
    "BaseAnalysisInputParams",
    "BaseAnalysisOutputParams",
    "BaseAnalysisTask",
    "BacktestBenchmark",
    "BacktestDimensions",
    "BaseBacktestInputParams",
    "BaseBacktestOutputParams",
    "BaseBacktestTask",
    "BaseETLInputParams",
    "BaseETLOutputParams",
    "BaseETLTask",
    "BasePredictInputParams",
    "BasePredictOutputParams",
    "BasePredictTask",
    "BaseTrainInputParams",
    "BaseTrainOutputParams",
    "BaseTrainTask",
    "TaskHandle",
    "TrainingCurve",
]
