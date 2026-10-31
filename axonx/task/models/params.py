"""Task inputs and results, including training, comparison and execution windows."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from .artifacts import (
    ArtifactRecord,
    PredictionProtocol,
    validate_protocol,
)
from .base import TaskModel, normalize_yyyymmdd
from .identity import (
    TaskType,
    task_type_from_id,
    validate_task_name,
    validate_upstream_task_ids,
)
from .reports import (
    BacktestPortfolioReport,
    ModelGroup,
    PortfolioDefinition,
    PredictionComparison,
    WindowResult,
)


class BaseInputParams(TaskModel):
    """Validated user-supplied parameters for one Task invocation."""

    model_config = ConfigDict(validate_assignment=True)
    task_name: str | None = None
    upstream_task_ids: list[str] = Field(
        default_factory=list,
        description="Direct upstream Task IDs for input dependencies; declaring them does not execute Tasks.",
    )

    @field_validator("task_name", mode="before")
    @classmethod
    def validate_task_name(cls, name: Any) -> str | None:
        if name is None or name == "":
            return None
        return validate_task_name(name)

    @field_validator("upstream_task_ids")
    @classmethod
    def validate_upstream_task_ids(cls, task_ids: list[str]) -> list[str]:
        return validate_upstream_task_ids(task_ids)

    def upstream_task_id(self, task_type: TaskType) -> str:
        """Return the single declared upstream Task ID of the requested type."""
        matches = [task_id for task_id in self.upstream_task_ids if task_type_from_id(task_id) == task_type]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ValueError(f"Multiple upstream tasks of type: {task_type.value}")
        raise ValueError(f"Missing upstream task: {task_type.value}")


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


class BasePortfolioOutputParams(BaseOutputParams):
    portfolios: list[PortfolioDefinition] = Field(min_length=1)
    protocol: dict[str, Any]

    @model_validator(mode="after")
    def validate_portfolios(self):
        identities = [report.portfolio_id for report in self.portfolios]
        if any(value in identities[:index] for index, value in enumerate(identities)):
            raise ValueError("Portfolio identities must be unique")
        for report in self.portfolios:
            if set(report.artifacts.values()) - self.artifacts.keys():
                raise ValueError("Portfolio references an unregistered artifact")
        return self

    @field_validator("protocol")
    @classmethod
    def validate_portfolio_protocol(cls, value):
        return validate_protocol(value, TaskType.PORTFOLIO)


class BaseBacktestOutputParams(BasePortfolioOutputParams):
    portfolios: list[BacktestPortfolioReport] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reports(self):
        if any(not {"daily", "summary"} <= report.artifacts.keys() for report in self.portfolios):
            raise ValueError("Every portfolio requires daily and summary artifacts")
        return self

    @field_validator("protocol")
    @classmethod
    def validate_portfolio_protocol(cls, value):
        return validate_protocol(value, TaskType.BACKTEST)


class BasePredictOutputParams(BaseOutputParams):
    """Describe the prediction artifact consumed by downstream tasks."""

    artifacts: dict[Literal["predictions"], ArtifactRecord] = Field(min_length=1)
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
    """Model index stored directly in a training Task's output_params."""

    feature_protocol: dict[str, Any]
    training_target: dict[str, Any] = Field(default_factory=dict)
    model_groups: list[ModelGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_models(self):
        validate_protocol(self.feature_protocol, TaskType.ETL)
        for index, group in enumerate(self.model_groups):
            if index:
                previous = self.model_groups[index - 1]
                if previous.use_to is None or previous.use_to > group.use_from:
                    raise ValueError("Model groups must be ordered and non-overlapping")
            for member in group.models.values():
                if member.model_artifact is not None and member.model_artifact not in self.artifacts:
                    raise ValueError("Model references an unregistered artifact")
        return self

    def select_groups(self, start: str | int, end: str | int) -> list[ModelGroup]:
        """Select completed groups covering an inclusive prediction interval."""
        start, end = normalize_yyyymmdd(start), normalize_yyyymmdd(end)
        if end < start:
            raise ValueError("end_date must not precede start_date")
        groups = [
            group
            for group in self.model_groups
            if group.use_from <= end and (group.use_to is None or start < group.use_to)
        ]
        covered = (
            bool(groups)
            and groups[0].use_from <= start
            and (groups[-1].use_to is None or groups[-1].use_to > end)
            and all(left.use_to == right.use_from for left, right in zip(groups, groups[1:]))
        )
        if not covered or any(member.state != "succeeded" for group in groups for member in group.models.values()):
            raise ValueError(f"No completed model group covering {start} through {end}")
        return groups

    def select_group(self, use_at: str | int) -> ModelGroup:
        return self.select_groups(use_at, use_at)[0]


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
