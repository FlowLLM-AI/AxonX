"""Stock research parameters, settings and output models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .protocol import validate_feature_protocol
from ...identity import normalize_yyyymmdd
from ...models.params import (
    BaseBacktestOutputParams,
    BaseETLOutputParams,
    BaseInputParams,
)


class PortfolioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_ns: list[int] = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20, 30])
    buy_cost_rate: float = Field(default=0.0005, ge=0, lt=1, description="Fee on executed buy notional.")
    sell_cost_rate: float = Field(default=0.0015, ge=0, lt=1, description="Fee on executed sell notional.")
    annual_risk_free_rate: float = Field(default=0.012, gt=-1, lt=1)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.98, gt=0, le=1)
    missing_market_as_suspension: bool = Field(
        default=False,
        description="Treat absent quotes and missing_data as suspensions: carry the last mark, block trading, "
        "and do not mark evaluation incomplete for these gaps.",
    )

    @field_validator("top_ns")
    @classmethod
    def positive_ns(cls, values: list[int]) -> list[int]:
        if not values or any(n <= 0 for n in values):
            raise ValueError("top_ns must contain positive integers")
        return sorted(set(values))

    def engine_config(self, *, holding_days: int | None) -> BacktestConfig:
        return BacktestConfig(
            top_ns=tuple(self.top_ns),
            holding_days=holding_days,
            buy_cost_rate=self.buy_cost_rate,
            sell_cost_rate=self.sell_cost_rate,
            annual_risk_free_rate=self.annual_risk_free_rate,
            annualization_days=self.annualization_days,
            minimum_index_weight_coverage=self.minimum_index_weight_coverage,
            missing_market_as_suspension=self.missing_market_as_suspension,
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
    market_file: Path | None = None
    calendar_file: Path | None = None
    labels_file: Path | None = None
    as_of_date: str | None = None

    @field_validator("as_of_date", mode="before")
    @classmethod
    def cutoff(cls, value: object) -> str | None:
        return normalize_yyyymmdd(value, optional=True)


class StockBacktestInput(StockPortfolioInput):
    holding_days: int = Field(default=1, ge=1)


class StockBacktestOutput(BaseBacktestOutputParams):
    signals_format: Literal["stock-signals-v1"]


class StockETLOutput(BaseETLOutputParams):
    protocol: dict

    @field_validator("protocol")
    @classmethod
    def validate_etl_protocol(cls, value):
        return validate_feature_protocol(value)
