"""Qlib Alpha158 data preparation, modeling and evaluation Tasks.

etl: Alpha158 datasets, market-state normalization and artifact publication.
analysis: Factor diagnostics and analysis reports.
train: LightGBM training, label presets and model publication.
predict: Full-cross-section prediction from published model collections.
backtest: Stock backtests using the shared portfolio ledger.
research: Typed composition of the independently observable research stages.
internal: Domain calculations, feature preparation and Qlib reference presets.
scripts: Local research comparison commands, invoked explicitly.
"""

from . import analysis, backtest, etl, internal, predict, research, scripts, train
from .analysis import FactorAnalysisInputParams, FactorAnalysisTask
from .backtest import Alpha158BacktestTask
from .etl import Alpha158InputParams, Alpha158Task
from .predict import LgbmPredictInputParams, LgbmPredictTask
from .research import Alpha158ResearchTask, ResearchInputParams, ResearchOutputParams
from .train import LgbmTrainInputParams, LgbmTrainTask

__all__ = [
    "Alpha158BacktestTask",
    "Alpha158InputParams",
    "Alpha158ResearchTask",
    "Alpha158Task",
    "FactorAnalysisInputParams",
    "FactorAnalysisTask",
    "LgbmPredictInputParams",
    "LgbmPredictTask",
    "LgbmTrainInputParams",
    "LgbmTrainTask",
    "ResearchInputParams",
    "ResearchOutputParams",
    "analysis",
    "backtest",
    "etl",
    "internal",
    "predict",
    "research",
    "scripts",
    "train",
]
