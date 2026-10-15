"""Shared dimensions and artifact references consumed by research report readers."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .online import OnlineCommit


class BacktestBenchmark(BaseModel):
    """One benchmark series exposed by a backtest artifact."""

    key: str
    label: str


class BacktestDimensions(BaseModel):
    """Dimensions needed to render standard backtest artifacts."""

    top_ns: list[int]
    holding_detail_top_n: int
    benchmarks: list[BacktestBenchmark]


class BacktestUniverse(BaseModel):
    """Plugin-owned selection definition; the framework owns result publication."""

    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestUniverseReport(BaseModel):
    """One independent portfolio report; artifact names reference the Task registry."""

    model_config = ConfigDict(extra="forbid")
    label: str
    parameters: dict[str, Any]
    dimensions: BacktestDimensions
    date_range: dict[str, str]
    days: int
    evaluation_status: str
    artifacts: dict[str, str]


class StockReportSettings(BaseModel):
    """The stock report uses the same portfolio artifact schemas as backtests."""

    model_config = ConfigDict(extra="forbid")
    signals_format: Literal["stock-signals-v1"]
    strategy_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    dimensions: BacktestDimensions
    date_range: dict[str, str]
    portfolio: dict[str, Any]
    score_selection: dict[str, Any]
    evaluation_status: Literal["done", "incomplete_market_data"]
    missing_dates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_settings(self):
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


STOCK_REPORT_ARTIFACTS = frozenset(
    {
        "predictions",
        "signal",
        "market",
        "signals",
        "orders",
        "positions",
        "trades",
        "daily",
        "summary",
        "prediction_protocol",
        "calendar",
        "input_features",
    }
)


class StockOnlineReport(BaseModel):
    """A report is one immutable publication; settings live in its protocol."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["stock_online"] = "stock_online"
    commit: OnlineCommit

    @model_validator(mode="after")
    def validate_report(self):
        settings = StockReportSettings.model_validate(self.commit.protocol.get("report"))
        if settings.date_range["end"] != self.commit.trade_date:
            raise ValueError("Online report must end at its committed signal date")
        if missing := STOCK_REPORT_ARTIFACTS - self.commit.artifacts.keys():
            raise ValueError(f"Incomplete stock online report: {sorted(missing)}")
        return self
