"""Task execution types, lifecycle states and operational categories."""

from enum import StrEnum


class TaskState(StrEnum):
    """Represent the durable lifecycle state of a task run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether no further execution transition is expected."""
        return self != TaskState.RUNNING


class TaskType(StrEnum):
    """Enumerate the supported task categories."""

    BASE = "base"
    COMPOSITE = "composite"
    API = "api"
    ETL = "etl"
    ANALYSIS = "analysis"
    TRAIN = "train"
    PREDICT = "predict"  # Offline prediction
    INFERENCE = "inference"  # Online inference
    BACKTEST = "backtest"


class TaskCategory(StrEnum):
    DATA_UPDATE = "data_update"
    ONLINE_PREDICTION = "online_prediction"
    COMPARISON = "comparison"
