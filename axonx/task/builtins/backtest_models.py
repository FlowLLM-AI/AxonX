"""Typed input and output contracts for the built-in backtest Task."""

from pydantic import Field

from ..core import BaseInputParams, BaseOutputParams


class BacktestOutputParams(BaseOutputParams):
    daily_file: str
    summary_file: str
    dimensions: dict
    protocol: dict
    date_range: dict[str, str]
    days: int


class BacktestInputParams(BaseInputParams):
    transaction_cost_rate: float = Field(
        default=0.002,
        ge=0.0,
        lt=1.0,
        description="Transaction cost as a decimal rate applied to daily portfolio turnover.",
    )
    annual_risk_free_rate: float = Field(
        default=0.012,
        gt=-1.0,
        lt=1.0,
        description="Annual risk-free rate used to calculate risk-adjusted returns.",
    )
    annualization_days: int = Field(
        default=252,
        gt=0,
        description="Number of trading days used to annualize return and risk metrics.",
    )
    minimum_index_weight_coverage: float = Field(
        default=0.90,
        gt=0.0,
        le=1.0,
        description="Minimum daily index weight coverage required for benchmark returns.",
    )
    index_filter: str = Field(
        default="",
        description="Optional comma-separated index codes, such as hs300,zz500. Leave blank to include all buyable stocks.",
    )
