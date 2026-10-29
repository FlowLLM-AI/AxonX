"""Qlib Alpha158 data preparation, modeling and evaluation Tasks.

etl: Alpha158 datasets, market-state normalization and artifact publication.
analysis: Factor diagnostics and analysis reports.
train: LightGBM training, label presets and model publication.
predict: Full-cross-section prediction from published model collections.
backtest: Stock backtests using the shared portfolio ledger.
research: Typed composition of the independently observable research stages.
comparison: Label/preset comparisons and their independently observable stages.
internal: Domain calculations, feature preparation and Qlib reference presets.
"""

from . import analysis, backtest, comparison, etl, internal, predict, research, train
from .analysis import FactorAnalysisInputParams, FactorAnalysisTask
from .backtest import Alpha158BacktestTask
from .comparison import ComparisonInputParams, ParameterComparisonTask
from .etl import Alpha158InputParams, Alpha158Task
from .predict import LgbmPredictInputParams, LgbmPredictTask
from .research import Alpha158ResearchTask, ResearchInputParams, ResearchOutputParams
from .train import LgbmTrainInputParams, LgbmTrainTask

__all__ = [
    "Alpha158BacktestTask",
    "Alpha158InputParams",
    "Alpha158ResearchTask",
    "Alpha158Task",
    "ComparisonInputParams",
    "FactorAnalysisInputParams",
    "FactorAnalysisTask",
    "LgbmPredictInputParams",
    "LgbmPredictTask",
    "LgbmTrainInputParams",
    "LgbmTrainTask",
    "ParameterComparisonTask",
    "ResearchInputParams",
    "ResearchOutputParams",
    "analysis",
    "backtest",
    "comparison",
    "etl",
    "internal",
    "predict",
    "research",
    "train",
]
