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

from .windows import DeadlineBudget, ExecutionWindow, WindowClock, WindowResult
from .realtime import BaseRealtimeApiInputParams, BaseRealtimeApiOutputParams, BaseRealtimeApiTask
from .inference import BaseInferenceInputParams, BaseInferenceOutputParams, BaseInferenceTask
from .compare import (
    BasePredictionCompareInputParams,
    BasePredictionCompareOutputParams,
    BasePredictionCompareTask,
    PredictionComparison,
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
    "DeadlineBudget",
    "ExecutionWindow",
    "WindowClock",
    "WindowResult",
    "BaseRealtimeApiInputParams",
    "BaseRealtimeApiOutputParams",
    "BaseRealtimeApiTask",
    "BaseInferenceInputParams",
    "BaseInferenceOutputParams",
    "BaseInferenceTask",
    "BasePredictionCompareInputParams",
    "BasePredictionCompareOutputParams",
    "BasePredictionCompareTask",
    "PredictionComparison",
]
