"""Validated Task inputs, outputs, training curves and prediction comparisons."""

from __future__ import annotations

import re
from math import isfinite
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import TASK_NAME_PATTERN
from ..task_enums import TaskType
from ..identity import parse_source_tasks, task_type_from_id
from .artifacts import (
    ArtifactRecord,
    PredictionProtocol,
    validate_protocol,
)
from .reports import BacktestUniverseReport

_TASK_NAME = re.compile(TASK_NAME_PATTERN)


class BaseInputParams(BaseModel):
    """Validated user-supplied parameters for one Task invocation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task_name: str | None = None
    source_tasks: str = Field(default="", description="Upstream Task IDs separated by ASCII commas.")

    @field_validator("task_name", mode="before")
    @classmethod
    def validate_task_name(cls, name: Any) -> str | None:
        if name is None or name == "":
            return None
        if not isinstance(name, str) or not _TASK_NAME.fullmatch(name):
            raise ValueError("task_name must contain 1-32 letters, digits, or hyphens")
        return name

    @field_validator("source_tasks")
    @classmethod
    def validate_source_tasks(cls, sources: str) -> str:
        return ",".join(parse_source_tasks(sources))

    def source_task(self, task_type: TaskType) -> str:
        matches = [
            task_id for task_id in parse_source_tasks(self.source_tasks) if task_type_from_id(task_id) == task_type
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ValueError(f"Multiple source tasks of type: {task_type.value}")
        raise ValueError(f"Missing source task: {task_type.value}")


class BaseOutputParams(BaseModel):
    """Validated Task result, including any produced artifacts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)


class BaseAnalysisOutputParams(BaseOutputParams):
    rows: int
    scores: dict[str, dict[str, float]] = Field(default_factory=dict)


class BaseETLInputParams(BaseInputParams):
    input_dir: Path = Field(description="Directory containing the source data to transform.")


class BaseETLOutputParams(BaseOutputParams):
    rows: int
    date_range: dict[str, str]
    feature_columns: list[str] = Field(default_factory=list)
    label_columns: list[str] = Field(default_factory=list)


class BaseBacktestOutputParams(BaseOutputParams):
    default_universe: str
    universes: dict[str, BacktestUniverseReport] = Field(min_length=1)
    protocol: dict[str, Any]

    @model_validator(mode="after")
    def validate_universes(self):
        if self.default_universe not in self.universes:
            raise ValueError("default_universe must reference a published report")
        for report in self.universes.values():
            if not {"daily", "summary"} <= report.artifacts.keys():
                raise ValueError("Every universe requires daily and summary artifacts")
            if set(report.artifacts.values()) - self.artifacts.keys():
                raise ValueError("Universe references an unregistered artifact")
        return self

    @field_validator("protocol")
    @classmethod
    def validate_backtest_protocol(cls, value):
        return validate_protocol(value, TaskType.BACKTEST)


class BasePredictOutputParams(BaseOutputParams):
    """Describe the prediction artifact consumed by downstream tasks."""

    rows: int
    date_range: dict[str, str]
    output_columns: list[str] = Field(default_factory=list)
    protocol: dict[str, Any]
    statistics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_prediction_protocol(self):
        protocol = PredictionProtocol.model_validate(self.protocol)
        if protocol.task_type != TaskType.PREDICT:
            raise ValueError("Prediction output differs from its protocol")
        return self


class TrainingCurve(BaseModel):
    """Aligned training history for one chart with up to two y-axis ranges.

    Each ``x[i]`` labels the same training point in every series. Producers
    may use iteration numbers, timestamps, or another ordered string label.
    ``y_left`` contains series with comparable units and numeric ranges on
    the primary axis. Use optional ``y_right`` only for a second group that
    needs an independent scale; do not mix substantially different scales
    within either group or add a third group.

    Every series has exactly ``len(x)`` finite samples, and names are unique
    across the two groups. A populated curve requires at least one left-axis
    series. Empty ``x`` and empty groups mean no curve data is available.
    """

    x: list[str] = Field(
        default_factory=list,
        description="Ordered labels shared by every series, e.g. iterations or timestamps.",
    )
    y_left: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Named series sharing the primary left y-axis value range.",
    )
    y_right: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Named series sharing an optional second value range on the right y-axis.",
    )

    @model_validator(mode="after")
    def validate_series(self):
        if not self.x and (self.y_left or self.y_right):
            raise ValueError("Training curve series require x-axis points")
        if self.x and not self.y_left:
            raise ValueError("A populated training curve requires a left-axis series")
        if self.y_left.keys() & self.y_right.keys():
            raise ValueError("Training curve series names must be unique across axes")
        for name, values in (*self.y_left.items(), *self.y_right.items()):
            if len(values) != len(self.x):
                raise ValueError(f"Training curve series {name!r} must match the x-axis length")
            if not all(isfinite(value) for value in values):
                raise ValueError(f"Training curve series {name!r} must contain finite values")
        return self


class BaseTrainOutputParams(BaseOutputParams):
    train_rows: int
    model_name: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    training_curve: TrainingCurve = Field(
        default_factory=TrainingCurve,
        description="Optional aligned training history with up to two value ranges, one per y-axis.",
    )

    @model_validator(mode="after")
    def validate_model_collection(self):
        if "model_manifest" not in self.artifacts:
            raise ValueError("Training output requires a model_manifest artifact")
        return self


class PredictionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    status: Literal["consistent", "different", "protocol_mismatch", "missing", "error"]
    reason: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)


class BasePredictionCompareInputParams(BaseInputParams):
    comparison_keys: list[str] = Field(min_length=1)

    @field_validator("comparison_keys")
    @classmethod
    def unique_keys(cls, keys: list[str]) -> list[str]:
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("comparison keys must be nonempty and unique")
        return keys


class BasePredictionCompareOutputParams(BaseOutputParams):
    comparisons: list[PredictionComparison] = Field(default_factory=list)
