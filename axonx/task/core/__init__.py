"""Core task contracts and built-in backtest."""

from .analysis import (
    BaseAnalysisInputParams,
    BaseAnalysisOutputParams,
    BaseAnalysisTask,
)
from .backtest import BacktestInputParams, BacktestOutputParams, BacktestTask
from .etl import BaseETLInputParams, BaseETLOutputParams, BaseETLTask
from .predict import BasePredictInputParams, BasePredictOutputParams, BasePredictTask
from .train import BaseTrainInputParams, BaseTrainOutputParams, BaseTrainTask, TrainingCurve

__all__ = [
    "BaseAnalysisInputParams",
    "BaseAnalysisOutputParams",
    "BaseAnalysisTask",
    "BaseETLInputParams",
    "BaseETLOutputParams",
    "BaseETLTask",
    "BasePredictInputParams",
    "BasePredictOutputParams",
    "BasePredictTask",
    "BaseTrainInputParams",
    "BaseTrainOutputParams",
    "BaseTrainTask",
    "TrainingCurve",
    "BacktestInputParams",
    "BacktestOutputParams",
    "BacktestTask",
]
