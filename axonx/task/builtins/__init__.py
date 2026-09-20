"""Built-in Tasks shipped with AxonX."""

from .backtest import BacktestTask
from .demo import DemoTask
from .dingtalk import SendDingTalkTask
from .tushare import DownloadTushareTask

__all__ = [
    "BacktestTask",
    "DemoTask",
    "DownloadTushareTask",
    "SendDingTalkTask",
]
