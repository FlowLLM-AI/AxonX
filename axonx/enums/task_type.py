"""Categories for data and model tasks."""

from enum import StrEnum


class TaskType(StrEnum):
    """Enumerate the supported task categories."""

    BASE = "base"
    API = "api"
    ETL = "etl"
    ANALYSIS = "analysis"
    TRAIN = "train"
    PREDICT = "predict"  # Offline prediction
    INFERENCE = "inference"  # Online inference
    BACKTEST = "backtest"
