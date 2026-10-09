"""Three Alpha158 layers share the framework position engine."""

from axonx_alpha158.backtest import Alpha158BacktestTask
from axonx_alpha158_factor.backtest import (
    Alpha158BacktestTask as FactorBacktestTask,
)


from axonx_alpha158_strategy.backtest import StrategyBacktestTask

from axonx.task.builtins.stock import BaseStockBacktestTask


def test_plugins_inherit_one_stock_backtest():
    assert issubclass(Alpha158BacktestTask, BaseStockBacktestTask)
    assert issubclass(FactorBacktestTask, BaseStockBacktestTask)
    assert Alpha158BacktestTask.calculate is FactorBacktestTask.calculate

    assert issubclass(FactorBacktestTask, Alpha158BacktestTask)
    assert issubclass(StrategyBacktestTask, FactorBacktestTask)
    assert StrategyBacktestTask.calculate is Alpha158BacktestTask.calculate
