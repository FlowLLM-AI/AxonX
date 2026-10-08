"""Stock portfolio accounting is provided by AxonX."""

from axonx.task.builtins.stock import BaseStockBacktestTask, StockBacktestInput


class Alpha158BacktestInputParams(StockBacktestInput):
    pass


class Alpha158BacktestTask(BaseStockBacktestTask):
    input_cls = Alpha158BacktestInputParams
