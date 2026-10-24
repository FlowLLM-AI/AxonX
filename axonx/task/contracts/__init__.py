"""Optional standard contracts for common data and model Task capabilities."""

from ..core import BaseInputParams
from ..core.clock import DeadlineBudget, WindowClock
from ..schemas.artifact import ArtifactRecord
from ..schemas.online import OnlineCommit, OnlineHistory
from ..schemas.reports import (
    BacktestBenchmark,
    BacktestDimensions,
    BacktestUniverse,
    BacktestUniverseReport,
    StockOnlineReport,
    StockReportSettings,
)
from .analysis import (
    BaseAnalysisOutputParams,
    BaseAnalysisTask,
)
from .backtest import BaseBacktestOutputParams, BaseBacktestTask
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
from .predict import BasePredictOutputParams, BasePredictTask
from .realtime import BaseRealtimeApiTask
from .train import (
    BaseTrainOutputParams,
    BaseTrainTask,
    TrainingCurve,
)
from .windows import ExecutionWindow, WindowInputParams, WindowOutputParams, WindowResult

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
