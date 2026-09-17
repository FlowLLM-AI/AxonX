"""Core task contracts, artifact storage, and built-in backtest."""

from .analysis import (
    BaseAnalysisInputParams,
    BaseAnalysisOutputParams,
    BaseAnalysisTask,
)
from .artifact_task import BaseArtifactTask
from .artifact_store import ArtifactStore
from .backtest import BacktestInputParams, BacktestOutputParams, BacktestTask
from .etl import BaseETLInputParams, BaseETLOutputParams, BaseETLTask
from .predict import BasePredictInputParams, BasePredictOutputParams, BasePredictTask
from .train import BaseTrainInputParams, BaseTrainOutputParams, BaseTrainTask

__all__ = [
    "BaseAnalysisInputParams",
    "BaseAnalysisOutputParams",
    "BaseAnalysisTask",
    "BaseArtifactTask",
    "ArtifactStore",
    "BaseETLInputParams",
    "BaseETLOutputParams",
    "BaseETLTask",
    "BasePredictInputParams",
    "BasePredictOutputParams",
    "BasePredictTask",
    "BaseTrainInputParams",
    "BaseTrainOutputParams",
    "BaseTrainTask",
    "BacktestInputParams",
    "BacktestOutputParams",
    "BacktestTask",
]
