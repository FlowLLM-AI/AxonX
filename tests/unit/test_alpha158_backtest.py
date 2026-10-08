"""Both Alpha158 plugins share the framework position engine."""

from axonx_alpha158.backtest import Alpha158BacktestTask
from axonx_alpha158_enhanced.backtest import (
    Alpha158BacktestTask as EnhancedBacktestTask,
)


from axonx.task.builtins.stock import BaseStockBacktestTask


def test_plugins_inherit_one_stock_backtest():
    assert issubclass(Alpha158BacktestTask, BaseStockBacktestTask)
    assert issubclass(EnhancedBacktestTask, BaseStockBacktestTask)
    assert Alpha158BacktestTask.calculate is EnhancedBacktestTask.calculate
