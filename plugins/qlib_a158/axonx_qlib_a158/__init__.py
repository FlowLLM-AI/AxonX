"""Qlib Alpha158 offline data preparation, modeling and evaluation Tasks.

etl: Alpha158 datasets, market-state normalization and artifact publication.
analysis: Factor diagnostics and analysis reports.
train: LightGBM training, label presets and model publication.
predict: Full-cross-section prediction from published model collections.
portfolio: Frozen signal rankings, portfolio plans and strategy identities.
backtest: Stock backtests using the shared portfolio ledger.
research: Typed composition of the independently observable research stages.
comparison: Label/preset comparisons and their independently observable stages.
internal: Domain calculations, feature preparation and Qlib reference presets.
"""

from . import analysis, backtest, comparison, etl, internal, portfolio, predict, research, train
from .analysis import FactorAnalysisInputParams, FactorAnalysisTask
from .backtest import Alpha158BacktestTask
from .comparison import ComparisonInputParams, ParameterComparisonTask
from .etl import Alpha158InputParams, Alpha158Task
from .portfolio import Alpha158PortfolioTask
from .predict import LgbmPredictInputParams, LgbmPredictTask
from .research import Alpha158ResearchTask, ResearchInputParams, ResearchOutputParams
from .train import LgbmTrainInputParams, LgbmTrainTask

__all__ = [
    "Alpha158BacktestTask",
    "Alpha158PortfolioTask",
    "portfolio",
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
