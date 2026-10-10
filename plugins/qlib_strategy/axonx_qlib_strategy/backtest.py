"""Rank retention and bounded daily replacements on the shared stock ledger."""

from dataclasses import dataclass
import math

from pydantic import Field
from axonx_qlib_a158.backtest import Alpha158BacktestTask as BaseTask
from axonx.task.builtins.stock.backtest import StockPortfolioInput, StockBacktestOutput


@dataclass(frozen=True)
class RankRetentionPolicy:
    replacement_fraction: float
    minimum_holding_days: int
    rank_buffer: float

    def replacement_limit(self, n: int) -> int:
        return max(1, math.floor(n * self.replacement_fraction + 1e-12))

    def should_exit(self, *, rank: int | None, age: int, n: int) -> bool:
        return age >= self.minimum_holding_days and (rank is None or rank > math.ceil(n * self.rank_buffer))


class StrategyBacktestInput(StockPortfolioInput):
    top_ns: list[int] = Field(default_factory=lambda: [20, 30])
    replacement_fraction: float = Field(
        default=0.2, gt=0, le=1, description="Daily count cap per side; initial entry exempt."
    )
    minimum_holding_days: int = Field(
        default=10, ge=0, description="Elapsed market days before a rank exit is allowed."
    )
    rank_buffer: float = Field(default=1.0, ge=1, description="Retain eligible holdings through ceil(N * rank_buffer).")


class StrategyBacktestTask(BaseTask):
    """Backtest factor predictions with rank retention and bounded daily replacements.

    Uses the framework cash, market valuation, order, position and trade artifacts.
    Missing quotes block exits. Initial entry is exempt from the count cap; retained
    position weights drift, so the count cap does not constrain transaction notional.
    """

    input_cls = StrategyBacktestInput
    input_params: StrategyBacktestInput

    def fixed_holding_days(self) -> None:
        return None

    def portfolio_policy(self) -> RankRetentionPolicy:
        p = self.input_params
        return RankRetentionPolicy(p.replacement_fraction, p.minimum_holding_days, p.rank_buffer)

    def build_output_params(self) -> StockBacktestOutput:
        output = super().build_output_params()
        output.protocol["qlib_deviations"]["strategy"] = (
            "Rank retention after minimum market-day holding, bounded daily fills per side, "
            "and normalized cash allocation; Qlib uses TopkDropout with fixed replacement count."
        )
        output.protocol.update(
            strategy="rank_retention",
            exit="After minimum_holding_days, sell worst-ranked holdings outside ceil(N * rank_buffer).",
            replacement_cap="Each side: max(1, floor(N * replacement_fraction)) filled orders; initial entry exempt.",
            allocation="New entries at most 1/N equity; retained weights drift; no top-ups.",
            planned_exit="No fixed expiry; planned_exit_date is null and exit_delayed is not applicable.",
        )
        return output
