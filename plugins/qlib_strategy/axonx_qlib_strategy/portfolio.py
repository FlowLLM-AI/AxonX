"""Rank retention and bounded replacements expressed as reusable portfolio plans."""

from pydantic import Field

from axonx.task.builtins.stock.models import StockPortfolioInput
from axonx.task.builtins.stock.portfolio import StockStrategy
from axonx_qlib_a158.portfolio import Alpha158PortfolioTask


class StrategyPortfolioInput(StockPortfolioInput):
    top_ns: list[int] = Field(default_factory=lambda: [20, 30])
    holding_days: None = None
    replacement_fraction: float = Field(default=0.2, gt=0, le=1, allow_inf_nan=False)
    minimum_holding_days: int = Field(default=10, ge=0)
    rank_buffer: float = Field(default=1.0, ge=1, allow_inf_nan=False)


class StrategyPortfolioTask(Alpha158PortfolioTask):
    input_cls = StrategyPortfolioInput
    input_params: StrategyPortfolioInput

    def strategy(self):
        p = self.input_params
        return StockStrategy(
            kind="rank_retention",
            holding_days=None,
            replacement_fraction=p.replacement_fraction,
            minimum_holding_days=p.minimum_holding_days,
            rank_buffer=p.rank_buffer,
        )
