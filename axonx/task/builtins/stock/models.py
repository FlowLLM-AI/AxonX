"""Stock research parameters, settings and output models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...models.artifacts import fingerprint, validate_protocol
from ...models.base import TaskModel, normalize_yyyymmdd
from ...models.identity import TaskType
from ...models.params import (
    BaseBacktestOutputParams,
    BaseETLOutputParams,
    BaseInputParams,
    BasePortfolioOutputParams,
)
from ...models.reports import BacktestDimensions, OnlineCommit, PortfolioUniverse


class PortfolioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_ns: list[int] = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20, 30])

    @field_validator("top_ns")
    @classmethod
    def positive_ns(cls, values: list[int]) -> list[int]:
        if not values or any(n <= 0 for n in values):
            raise ValueError("top_ns must contain positive integers")
        return sorted(set(values))


class BacktestSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buy_cost_rate: float = Field(default=0.0005, ge=0, lt=1)
    sell_cost_rate: float = Field(default=0.0015, ge=0, lt=1)
    annual_risk_free_rate: float = Field(default=0.012, gt=-1, lt=1)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.98, gt=0, le=1)
    missing_market_as_suspension: bool = False

    def engine_config(self, *, top_ns: tuple[int, ...], holding_days: int | None) -> BacktestConfig:
        return BacktestConfig(
            **self.model_dump(include=set(BacktestSettings.model_fields)), top_ns=top_ns, holding_days=holding_days
        )


@dataclass(frozen=True)
class BacktestConfig:
    top_ns: tuple[int, ...] = (1, 2, 3, 5, 10, 20, 30)
    holding_days: int | None = 1
    annual_risk_free_rate: float = 0.012
    annualization_days: int = 252
    minimum_index_weight_coverage: float = 0.98
    buy_cost_rate: float = 0.0005
    sell_cost_rate: float = 0.0015
    missing_market_as_suspension: bool = False


class StockPortfolioInput(PortfolioSettings, BaseInputParams):
    input_file: Path | None = None
    score_columns: dict[str, str] | None = None
    holding_days: int = Field(default=1, ge=1)
    strategies: list[dict[str, Any]] | None = Field(default=None, min_length=1)


class StockPortfolioOutput(BasePortfolioOutputParams):
    signals_format: Literal["stock-signals-v3"]
    score_column: str = Field(min_length=1)
    universes: list[PortfolioUniverse] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_plans(self):
        if len({u.key for u in self.universes}) != len(self.universes):
            raise ValueError("Universe keys must be unique")
        for plan in self.portfolios:
            if "rankings" not in plan.artifacts:
                raise ValueError("Stock portfolios require rankings")
            if any(key not in self.artifacts for key in plan.artifacts.values()):
                raise ValueError("Portfolio artifacts must be published")
            identity = plan.portfolio_id
            if (
                not isinstance(identity.get("top_n"), int)
                or isinstance(identity["top_n"], bool)
                or identity["top_n"] < 1
            ):
                raise ValueError("Stock portfolio top_n must be a positive integer")
            if identity.get("allocation") != "equal_slot":
                raise ValueError("Unknown stock allocation")
        return self


class StockBacktestInput(BacktestSettings, BaseInputParams):
    market_file: Path | None = None
    calendar_file: Path | None = None
    labels_file: Path | None = None
    as_of_date: str | None = None
    portfolio_ids: list[dict[str, Any]] | None = Field(default=None, min_length=1)

    @field_validator("as_of_date", mode="before")
    @classmethod
    def cutoff(cls, value: object) -> str | None:
        return normalize_yyyymmdd(value, optional=True)


class StockBacktestOutput(BaseBacktestOutputParams):
    signals_format: Literal["stock-signals-v3"]


class StockETLOutput(BaseETLOutputParams):
    protocol: dict

    @field_validator("protocol")
    @classmethod
    def validate_etl_protocol(cls, value):
        # Feature compatibility and family-specific semantics belong to the plugin.
        return validate_protocol(value, TaskType.ETL)


def portfolio_key(identity: dict) -> str:
    """Keep an ensemble's portfolio series stable when its trained members roll."""
    selection = dict(identity.get("score_selection", {}))
    if selection.get("method") in {"mean", "rank_mean"}:
        selection.pop("seeds", None)
    return fingerprint(identity | {"score_selection": selection})


class StockReportSettings(TaskModel):
    """Daily display ledgers and stable identities; inference owns full execution evidence."""

    signals_format: Literal["stock-signals-v3"]
    score_column: str = Field(min_length=1)
    strategy_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    dimensions: BacktestDimensions
    date_range: dict[str, str]
    portfolio: dict[str, Any]
    portfolios: dict[str, dict[str, Any]] = Field(min_length=1)
    score_selection: dict[str, Any]
    evaluation_status: Literal["done", "incomplete_market_data"]
    missing_dates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_settings(self):
        if any(key != portfolio_key(identity) for key, identity in self.portfolios.items()):
            raise ValueError("Portfolio keys differ from their identities")
        start, end = (self.date_range.get(key, "") for key in ("start", "end"))
        for value in (start, end, *self.missing_dates):
            normalize_yyyymmdd(value)
        if start > end or any(not start <= value <= end for value in self.missing_dates):
            raise ValueError("Invalid online report date range")
        return self


STOCK_REPORT_ARTIFACTS = frozenset(
    {
        "predictions",
        "rankings",
        "market",
        "orders",
        "positions",
        "trades",
        "daily",
        "summary",
    }
)


class StockOnlineReport(TaskModel):
    """A report is one immutable publication; settings live in its protocol."""

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
