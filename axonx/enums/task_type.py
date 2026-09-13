"""Categories for data and model tasks."""

from enum import StrEnum


class TaskType(StrEnum):
    """Enumerate the supported task categories."""

    INGESTION = "ingestion"
    ETL = "etl"
    ANALYSIS = "analysis"
    TRAINING = "training"
    PREDICT = "predict"  # Offline prediction
    INFERENCE = "inference"  # Online inference
    BACKTEST = "backtest"
