"""Research result details: training, comparison, windows, backtests and online history."""

from __future__ import annotations

import json
from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .artifacts import ArtifactRecord, Protocol, validate_protocol
from .base import DateString, TaskModel
from .identity import TaskType


class TrainingCurve(TaskModel):
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


class ModelMember(TaskModel):
    """One named final model and its training record within a model group."""

    model: dict[str, Any]
    model_artifact: str | None = None
    state: Literal["pending", "running", "succeeded", "failed"] = "pending"
    train_rows: int = Field(default=0, ge=0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    training_curve: TrainingCurve = Field(default_factory=TrainingCurve)
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    error: str = ""

    @model_validator(mode="after")
    def validate_artifact(self):
        if self.state == "succeeded" and not self.model_artifact:
            raise ValueError("A completed model requires its final artifact")
        return self


class ModelGroup(TaskModel):
    """Models sharing one training range and half-open use interval."""

    train_start: DateString
    train_end_exclusive: DateString
    use_from: DateString
    use_to: DateString | None = None
    models: dict[str, ModelMember] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_window(self):
        if not self.train_start < self.train_end_exclusive <= self.use_from:
            raise ValueError("Require train_start < train_end_exclusive <= use_from")
        if self.use_to is not None and self.use_to <= self.use_from:
            raise ValueError("Model use_to must follow use_from")
        if any(not name or "/" in name or "\\" in name for name in self.models):
            raise ValueError("Model names must be nonempty file names")
        return self


class PredictionComparison(TaskModel):
    key: str
    status: Literal["consistent", "different", "protocol_mismatch", "missing", "error"]
    reason: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)


class WindowResult(TaskModel):
    key: str
    status: Literal["done", "skipped", "incomplete", "failed"]
    reason: str = ""
    commit_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    committed_at: AwareDatetime | None = None
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    rows: int = Field(default=0, ge=0)
    coverage: float | None = Field(default=None, ge=0, le=1)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_commit(self):
        if (self.commit_id is None) != (self.committed_at is None):
            raise ValueError("commit_id and committed_at must be supplied together")
        if self.commit_id is not None and self.status != "done":
            raise ValueError("Only completed windows may publish a commit")
        return self


class OnlineCommit(TaskModel):
    commit_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    task_id: str = Field(min_length=1)
    started_at: AwareDatetime
    trade_date: DateString = Field(pattern=r"^\d{8}$")
    trade_time: str = Field(pattern=r"^\d{4}$")
    revision: int = Field(ge=1)
    committed_at: AwareDatetime
    model_identity: dict[str, str] = Field(min_length=1)
    protocol: dict[str, Any]
    artifacts: dict[str, ArtifactRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_commit(self):
        validate_protocol(self.protocol, TaskType.INFERENCE)
        report = self.protocol.get("report", {})
        if not isinstance(report, dict):
            raise ValueError("Online report settings must be an object")
        if int(self.trade_time[:2]) > 23 or int(self.trade_time[2:]) > 59:
            raise ValueError("Invalid online signal time")
        return self


class OnlineHistory(Protocol):
    task_type: Literal[TaskType.INFERENCE] = TaskType.INFERENCE
    kind: Literal["online_history"] = "online_history"
    strategy_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    commits: list[OnlineCommit] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_commits(self):
        identities = [item.commit_id for item in self.commits]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate online commit")
        if any(
            c.protocol.get("report", {}).get("strategy_identity", self.strategy_identity) != self.strategy_identity
            for c in self.commits
        ):
            raise ValueError("Online commit strategy differs from its history")
        signals = set()
        for item in self.commits:
            key = (item.trade_date, item.trade_time)
            if key in signals:
                raise ValueError("Duplicate daily online signal")
            signals.add(key)
        return self


class BacktestBenchmark(TaskModel):
    """One benchmark series exposed by a backtest artifact."""

    key: str
    label: str


class BacktestDimensions(TaskModel):
    """Dimensions needed to render standard backtest artifacts."""

    top_ns: list[Annotated[int, Field(gt=0)]] = Field(min_length=1)
    holding_detail_top_n: int = Field(gt=0)
    benchmarks: list[BacktestBenchmark]

    @field_validator("top_ns")
    @classmethod
    def unique_top_ns(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)):
            raise ValueError("top_ns must be unique")
        return values


class PortfolioUniverse(TaskModel):
    """Plugin-owned selection definition; the framework owns result publication."""

    key: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class PortfolioDefinition(TaskModel):
    """A readable, plugin-owned identity and references to immutable selection artifacts."""

    portfolio_id: dict[str, Any] = Field(min_length=1)
    artifacts: dict[str, str]

    @field_validator("portfolio_id")
    @classmethod
    def validate_identity(cls, value):
        # JSON disallows non-finite numbers; key order is not part of identity.
        json.dumps(value, allow_nan=False, sort_keys=True)
        return value


class BacktestPortfolioReport(PortfolioDefinition):
    dimensions: BacktestDimensions
    date_range: dict[str, str]
    days: int
    evaluation_status: str
