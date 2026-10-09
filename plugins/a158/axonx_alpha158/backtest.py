"""Stock portfolio accounting is provided by AxonX."""

from axonx.task.builtins.stock import BaseStockBacktestTask, StockBacktestInput


class Alpha158BacktestInputParams(StockBacktestInput):
    pass


class Alpha158BacktestTask(BaseStockBacktestTask):
    """Evaluate Alpha158 predictions with the shared stock cash and position ledger.

    Reads independent market and calendar artifacts, applies fixed holding expiry
    and executed-side fees, and writes daily, period, order, position and trade
    artifacts with explicit missing-market-data evaluation status.
    """

    input_cls = Alpha158BacktestInputParams
