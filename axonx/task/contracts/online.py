"""Portable, immutable online publications; algorithms remain in plugins."""

from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ...enums import TaskType
from ..protocol import Protocol, validate_protocol
from .backtest import BacktestDimensions


class OnlineArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value):
        if value.startswith("/") or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Online artifact must be a relative task path")
        return value


class OnlineCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commit_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    trade_date: str = Field(pattern=r"^\d{8}$")
    trade_time: str = Field(pattern=r"^\d{4}$")
    revision: int = Field(ge=1)
    committed_at: AwareDatetime
    model_identity: dict[str, str] = Field(min_length=1)
    protocol: dict[str, Any]
    artifacts: dict[str, OnlineArtifact] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_date(self):
        validate_protocol(self.protocol, TaskType.INFERENCE)
        date(
            int(self.trade_date[:4]),
            int(self.trade_date[4:6]),
            int(self.trade_date[6:]),
        )
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
        if len({c.task_id for c in self.commits}) > 1:
            raise ValueError("Online history must belong to one Task")
        if any(
            c.protocol.get("report", {}).get("strategy_identity", self.strategy_identity) != self.strategy_identity
            for c in self.commits
        ):
            raise ValueError("Online commit strategy differs from its history")
        revisions: dict[tuple[str, str], int] = {}
        for item in self.commits:
            key = (item.trade_date, item.trade_time)
            revisions[key] = revisions.get(key, 0) + 1
            if item.revision != revisions[key]:
                raise ValueError("Online revisions must be consecutive")
        return self

    def active(self, as_of: str | None = None) -> list[OnlineCommit]:
        """Last revision wins; later reports require replay after a historical revision."""
        latest = {(item.trade_date, item.trade_time): item for item in self.commits}
        return [latest[key] for key in sorted(latest) if as_of is None or key[0] <= as_of]

    def report_is_current(self, commit: OnlineCommit) -> bool:
        index = next((i for i, item in enumerate(self.commits) if item.commit_id == commit.commit_id), None)
        return index is not None and not any(
            (item.trade_date, item.trade_time) <= (commit.trade_date, commit.trade_time)
            for item in self.commits[index + 1 :]
        )


class StockOnlineReport(BaseModel):
    """The stock report uses the same portfolio artifact schemas as backtests."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["stock_online"] = "stock_online"
    commit: OnlineCommit
    strategy_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    dimensions: BacktestDimensions
    date_range: dict[str, str]
    portfolio: dict[str, Any]
    score_selection: dict[str, Any]
    evaluation_status: Literal["done", "incomplete_market_data"]
    missing_dates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_artifacts(self):
        required = {
            "predictions",
            "signal",
            "market",
            "signals",
            "targets",
            "orders",
            "positions",
            "trades",
            "daily",
            "summary",
            "prediction_protocol",
            "calendar",
            "input_features",
        }
        if missing := required - self.commit.artifacts.keys():
            raise ValueError(f"Incomplete stock online report: {sorted(missing)}")
        if self.date_range.get("end") != self.commit.trade_date:
            raise ValueError("Online report must end at its committed signal date")
        if self.model_dump(mode="json", exclude={"kind", "commit"}) != self.commit.protocol.get("report"):
            raise ValueError("Online report settings differ from its commit")
        start, end = (self.date_range.get(key, "") for key in ("start", "end"))
        for value in (start, end, *self.missing_dates):
            if len(value) != 8 or not value.isdigit():
                raise ValueError("Invalid online report date")
            date(int(value[:4]), int(value[4:6]), int(value[6:]))
        if start > end or any(not start <= value <= end for value in self.missing_dates):
            raise ValueError("Invalid online report date range")
        if (
            not self.dimensions.top_ns
            or any(n <= 0 for n in self.dimensions.top_ns)
            or len(set(self.dimensions.top_ns)) != len(self.dimensions.top_ns)
            or self.dimensions.holding_detail_top_n <= 0
        ):
            raise ValueError("Invalid online report dimensions")
        return self
