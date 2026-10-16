"""Operational purpose, independent of Task execution type and storage identity."""

from enum import StrEnum


class TaskCategory(StrEnum):
    DATA_UPDATE = "data_update"
    ONLINE_PREDICTION = "online_prediction"
    COMPARISON = "comparison"
