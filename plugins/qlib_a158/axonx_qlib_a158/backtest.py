"""Stock portfolio accounting is provided by AxonX."""

from axonx.task.builtins.stock import BaseStockBacktestTask, StockBacktestInput as Alpha158BacktestInputParams
from axonx.task.builtins.stock.backtest import StockBacktestOutput

from .internal.reference import DEVIATIONS, QLIB_REFERENCE


class Alpha158BacktestTask(BaseStockBacktestTask):
    """Evaluate Alpha158 predictions with the shared stock cash and position ledger.

    Reads independent market and calendar artifacts, applies fixed holding expiry
    and executed-side fees, and writes daily, period, order, position and trade
    artifacts with explicit missing-market-data evaluation status.
    """

    input_cls = Alpha158BacktestInputParams

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
