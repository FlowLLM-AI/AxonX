"""Built-in Tasks shipped with AxonX."""

from .demo import DemoTask
from .dingtalk import SendDingTalkTask
from .tushare import DownloadTushareTask

__all__ = [
    "DemoTask",
    "DownloadTushareTask",
    "SendDingTalkTask",
]
