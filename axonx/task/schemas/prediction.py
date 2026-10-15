"""Shared identity and scope of offline and online predictions."""

from typing import Literal

from pydantic import Field, model_validator

from ...enums import TaskType
from .protocol import Protocol


class PredictionProtocol(Protocol):
    task_type: Literal[TaskType.PREDICT, TaskType.INFERENCE]
    model_identity: dict[str, str] = Field(min_length=1)
    dates: list[str] = Field(min_length=1)
    score_columns: dict[str, str] = Field(min_length=1)
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_scope(self):
        if self.dates != sorted(set(self.dates)) or any(not day for day in self.dates):
            raise ValueError("Prediction dates must be nonempty, sorted and unique")
        if any(not key or not value for key, value in self.score_columns.items()):
            raise ValueError("Prediction member IDs and score columns must be nonempty")
        if len(set(self.score_columns.values())) != len(self.score_columns):
            raise ValueError("Prediction members must have distinct score columns")
        return self
