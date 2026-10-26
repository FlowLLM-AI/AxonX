"""Task inputs and results, including training, comparison and execution windows."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from .artifacts import (
    ArtifactRecord,
    PredictionProtocol,
    validate_protocol,
)
from .base import TaskModel
from .identity import TaskType, parse_source_tasks, task_type_from_id, validate_task_name
from .reports import BacktestUniverseReport, PredictionComparison, TrainingCurve, WindowResult


class BaseInputParams(TaskModel):
    """Validated user-supplied parameters for one Task invocation."""

    model_config = ConfigDict(validate_assignment=True)
    task_name: str | None = None
    source_tasks: str = Field(default="", description="Upstream Task IDs separated by ASCII commas.")

    @field_validator("task_name", mode="before")
    @classmethod
    def validate_task_name(cls, name: Any) -> str | None:
        if name is None or name == "":
            return None
        return validate_task_name(name)

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


class BaseOutputParams(TaskModel):
    """Validated Task result, including any produced artifacts."""

    model_config = ConfigDict(populate_by_name=True)
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

    @field_validator("protocol")
    @classmethod
    def validate_prediction_protocol(cls, value: dict[str, Any]) -> dict[str, Any]:
        protocol = PredictionProtocol.model_validate(value)
        if protocol.task_type != TaskType.PREDICT:
            raise ValueError("Prediction output differs from its protocol")
        return value


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


class ExecutionWindow(TaskModel):
    key: str = Field(min_length=1)
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_at.astimezone(UTC) <= self.start_at.astimezone(UTC):
            raise ValueError("end_at must be after start_at")
        return self


class WindowOutputParams(BaseOutputParams):
    windows: list[WindowResult] = Field(default_factory=list)


class WindowInputParams(BaseInputParams):
    windows: list[ExecutionWindow] = Field(min_length=1)
    poll_interval_seconds: float = Field(default=1, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_windows(self):
        keys = [window.key for window in self.windows]
        if len(keys) != len(set(keys)):
            raise ValueError("window keys must be unique")
        if self.windows != sorted(self.windows, key=lambda window: window.start_at.astimezone(UTC)):
            raise ValueError("windows must be ordered by start_at")
        return self


class BaseInferenceOutputParams(WindowOutputParams):
    model_identity: dict[str, str]
