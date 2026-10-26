"""Qlib Alpha158 data preparation, modeling and evaluation Tasks.

etl: Alpha158 datasets, market-state normalization and artifact publication.
analysis: Factor diagnostics and analysis reports.
train: LightGBM training, label presets and model publication.
predict: Full-cross-section prediction from published model collections.
backtest: Stock backtests using the shared portfolio ledger.
internal: Domain calculations, feature preparation and Qlib reference presets.
scripts: Local research comparison commands, invoked explicitly.
"""

from . import analysis, backtest, etl, internal, predict, scripts, train
from .analysis import FactorAnalysisInputParams, FactorAnalysisTask
from .backtest import Alpha158BacktestInputParams, Alpha158BacktestTask
from .etl import Alpha158InputParams, Alpha158Task
from .predict import LgbmPredictInputParams, LgbmPredictTask
from .train import LgbmTrainInputParams, LgbmTrainTask

__all__ = [
    "Alpha158BacktestInputParams",
    "Alpha158BacktestTask",
    "Alpha158InputParams",
    "Alpha158Task",
    "FactorAnalysisInputParams",
    "FactorAnalysisTask",
    "LgbmPredictInputParams",
    "LgbmPredictTask",
    "LgbmTrainInputParams",
    "LgbmTrainTask",
    "analysis",
    "backtest",
    "etl",
    "internal",
    "predict",
    "scripts",
    "train",
]
