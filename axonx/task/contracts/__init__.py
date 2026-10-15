"""Optional standard contracts for common data and model Task capabilities."""

from ..artifact import ArtifactRecord
from ..core import BaseInputParams
from .analysis import (
    BaseAnalysisOutputParams,
    BaseAnalysisTask,
)
from .backtest import (
    BacktestBenchmark,
    BacktestDimensions,
    BacktestUniverse,
    BacktestUniverseReport,
    BaseBacktestOutputParams,
    BaseBacktestTask,
)
from .compare import (
    BasePredictionCompareInputParams,
    BasePredictionCompareOutputParams,
    BasePredictionCompareTask,
    PredictionComparison,
)
from .etl import BaseETLInputParams, BaseETLOutputParams, BaseETLTask
from .inference import (
    BaseInferenceOutputParams,
    BaseInferenceTask,
)
from .online import OnlineCommit, OnlineHistory, StockOnlineReport, StockReportSettings
from .predict import BasePredictOutputParams, BasePredictTask
from .realtime import BaseRealtimeApiTask
from .submission import TaskHandle
from .train import (
    BaseTrainOutputParams,
    BaseTrainTask,
    TrainingCurve,
)
from .windows import (
    DeadlineBudget,
    ExecutionWindow,
    WindowClock,
    WindowInputParams,
    WindowOutputParams,
    WindowResult,
)

__all__ = [
    "BacktestUniverse",
    "BacktestUniverseReport",
    "BaseAnalysisOutputParams",
    "BaseAnalysisTask",
    "BacktestBenchmark",
    "BacktestDimensions",
    "BaseBacktestOutputParams",
    "BaseBacktestTask",
    "BaseETLInputParams",
    "BaseETLOutputParams",
    "BaseETLTask",
    "BasePredictOutputParams",
    "BasePredictTask",
    "BaseTrainOutputParams",
    "BaseTrainTask",
    "BaseInputParams",
    "WindowInputParams",
    "TaskHandle",
    "TrainingCurve",
    "DeadlineBudget",
    "ExecutionWindow",
    "WindowClock",
    "WindowResult",
    "WindowOutputParams",
    "BaseRealtimeApiTask",
    "BaseInferenceOutputParams",
    "BaseInferenceTask",
    "ArtifactRecord",
    "StockReportSettings",
    "OnlineCommit",
    "OnlineHistory",
    "StockOnlineReport",
    "BasePredictionCompareInputParams",
    "BasePredictionCompareOutputParams",
    "BasePredictionCompareTask",
    "PredictionComparison",
]
