"""Stock portfolio accounting is provided by AxonX."""

from pydantic import Field

from axonx.task.builtins.stock import BaseStockBacktestTask, StockBacktestInput
from axonx.task.builtins.stock.backtest import StockBacktestOutput
from axonx.task.builtins.stock.engine import BacktestConfig

from .internal.reference import DEVIATIONS, QLIB_REFERENCE


class Alpha158BacktestInputParams(StockBacktestInput):
    buy_cost_rate: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        description="Buy notional fee rate; None uses transaction_cost_rate.",
    )
    sell_cost_rate: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        description="Sell notional fee rate; None uses transaction_cost_rate.",
    )


class Alpha158BacktestTask(BaseStockBacktestTask):
    """Evaluate Alpha158 predictions with the shared stock cash and position ledger.

    Reads independent market and calendar artifacts, applies fixed holding expiry
    and executed-side fees, and writes daily, period, order, position and trade
    artifacts with explicit missing-market-data evaluation status.
    """

    input_cls = Alpha158BacktestInputParams

    def calculate(self) -> None:
        """Require shared-engine support when an explicit side fee is selected."""
        p = self.input_params
        if (p.buy_cost_rate is not None or p.sell_cost_rate is not None) and not {
            "buy_cost_rate",
            "sell_cost_rate",
        }.issubset(BacktestConfig.__dataclass_fields__):
            raise RuntimeError("Separate buy/sell fees require AxonX core with buy_cost_rate/sell_cost_rate support.")
        super().calculate()

    def build_output_params(self) -> StockBacktestOutput:
        # The shared ledger uses official price limits, configurable side fees
        # and compound equity. Positions use normalized cash without round lots
        # or a minimum monetary fee; fixed expiry defines the portfolio policy.
        output = super().build_output_params()
        output.protocol.update(
            qlib_reference=QLIB_REFERENCE,
            qlib_deviations={key: DEVIATIONS[key] for key in ("execution", "limits", "strategy", "evaluation")},
        )
        return output
