"""Portable artifact records and protocol headers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .base import DateString, TaskModel, normalize_yyyymmdd
from .identity import TaskType


class ArtifactRecord(TaskModel):
    model_config = ConfigDict(frozen=True)
    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    revision: str = Field(pattern=r"^\d+:\d+$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value):
        if value.startswith("/") or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Artifact must be a relative task path")
        return value


PROTOCOL_VERSION = 1


class Protocol(TaskModel):
    """Plugins extend the payload; the framework owns version and producer type."""

    model_config = ConfigDict(extra="allow")
    version: Literal[1]
    task_type: TaskType

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, value):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Protocol version must be an integer")
        return value


def task_protocol(task_type: TaskType, **payload: Any) -> dict:
    return Protocol(version=PROTOCOL_VERSION, task_type=task_type, **payload).model_dump(mode="json")


def validate_protocol(value: dict, *task_types: TaskType) -> dict:
    header = Protocol.model_validate(value)
    if task_types and header.task_type not in task_types:
        raise ValueError(f"Expected protocol for {task_types}, got {header.task_type}")
    return value


def fingerprint(value: Any) -> str:
    """Hash semantic content deterministically, independent of mapping order."""
    content = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode()).hexdigest()


class PredictionWindow(TaskModel):
    """A model group used over a half-open prediction interval."""

    prediction_start: DateString
    prediction_end_exclusive: DateString
    model_identity: dict[str, str] = Field(min_length=1)
    models: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_window(self):
        if self.prediction_start >= self.prediction_end_exclusive:
            raise ValueError("Prediction window must have start < end_exclusive")
        if any(not key or not value for key, value in self.models.items()):
            raise ValueError("Prediction model names must be nonempty")
        return self


class PredictionProtocol(Protocol):
    """Score semantics; file revisions and execution lineage belong to metadata."""

    task_type: Literal[TaskType.PREDICT, TaskType.INFERENCE]
    score_columns: dict[str, str] = Field(min_length=1)
    windows: list[PredictionWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self):
        if any(not key or not value for key, value in self.score_columns.items()):
            raise ValueError("Prediction member IDs and score columns must be nonempty")
        if len(set(self.score_columns.values())) != len(self.score_columns):
            raise ValueError("Prediction members must have distinct score columns")
        if self.task_type == TaskType.PREDICT and not self.windows:
            raise ValueError("Offline predictions require model use windows")
        if self.task_type == TaskType.INFERENCE and self.windows:
            raise ValueError("Online model identity and date belong to the commit")
        for index, window in enumerate(self.windows):
            if window.models.keys() != self.score_columns.keys():
                raise ValueError("Prediction window models must match score members")
            if index and self.windows[index - 1].prediction_end_exclusive > window.prediction_start:
                raise ValueError("Prediction windows must be ordered and non-overlapping")
        return self

    def window_for(self, day: str | int) -> PredictionWindow:
        date = normalize_yyyymmdd(day)
        for window in self.windows:
            if window.prediction_start <= date < window.prediction_end_exclusive:
                return window
        raise ValueError(f"No prediction model window for {date}")


def prediction_protocol(
    task_type: TaskType,
    score_columns: dict[str, str],
    **payload,
) -> dict:
    return PredictionProtocol(
        version=PROTOCOL_VERSION,
        task_type=task_type,
        score_columns=score_columns,
        **payload,
    ).model_dump(mode="json", exclude_defaults=True)
