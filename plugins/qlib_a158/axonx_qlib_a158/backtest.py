"""Stock portfolio accounting is provided by AxonX."""

import polars as pl

from axonx.task.builtins.stock.backtest import BaseStockBacktestTask
from axonx.task.builtins.stock.data import KEYS
from axonx.task.builtins.stock.models import (
    StockBacktestInput as Alpha158BacktestInputParams,
)
from axonx.task.builtins.stock.models import StockBacktestOutput
from axonx.task.models.reports import BacktestUniverse

from .internal.reference import DEVIATIONS, QLIB_REFERENCE


class Alpha158BacktestTask(BaseStockBacktestTask):
    """Evaluate Alpha158 predictions with the shared stock cash and position ledger.

    Reads independent market and calendar artifacts, applies fixed holding expiry
    and executed-side fees, and writes daily, period, order, position and trade
    artifacts with explicit missing-market-data evaluation status.
    """

    input_cls = Alpha158BacktestInputParams

    def resolve_inputs(self):
        super().resolve_inputs()
        # The plugin evaluates through its final signal date by default. A caller
        # can explicitly extend as_of_date to value or settle remaining positions.
        if self.input_params.as_of_date is None:
            self.input_params.as_of_date = self.state["signals"]["trade_date"].max()

    def build_universes(self):
        yield BacktestUniverse(key="all", label="全市场")
        yield BacktestUniverse(key="hs300", label="沪深300", parameters={"index": "hs300"})

    def select_universe(self, signals, universe):
        if universe.key == "hs300":
            signals = signals.filter(pl.col("index_weight_hs300") > 0)
        return signals.select(*KEYS)

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
