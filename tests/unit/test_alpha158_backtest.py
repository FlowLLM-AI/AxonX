"""Plugin policies share the framework position engine."""

from axonx_qlib_a158.backtest import Alpha158BacktestTask
from axonx_qlib_strategy.backtest import StrategyBacktestTask
from axonx.task.builtins.stock import BaseStockBacktestTask


def test_plugins_inherit_one_stock_backtest():
    assert issubclass(Alpha158BacktestTask, BaseStockBacktestTask)
    assert issubclass(StrategyBacktestTask, Alpha158BacktestTask)
    assert StrategyBacktestTask.calculate is Alpha158BacktestTask.calculate
