"""Bundled Task implementations and reusable domain capabilities.

demo: Arithmetic workflow demonstrating synchronous steps, progress and failure handling.
dingtalk: Application-robot authentication, group notifications and the notification Task.
tushare: Retrying API access, normalized dataset storage and the download Task.
stock: Stock artifact protocols, portfolio accounting, backtest orchestration and reports.
"""

from . import demo, dingtalk, stock, tushare

__all__ = [
    "demo",
    "dingtalk",
    "stock",
    "tushare",
]
