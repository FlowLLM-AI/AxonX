"""Alpha158 strategy layer inherits factor research and changes only backtesting."""

from .backtest import StrategyBacktestInput, StrategyBacktestTask

__all__ = ["StrategyBacktestInput", "StrategyBacktestTask"]
