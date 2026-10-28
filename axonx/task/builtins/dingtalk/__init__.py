"""DingTalk notification client and Task contracts.

client: Authentication, recipient validation and text/Markdown message delivery.
task: Validated message inputs, delivery outputs and SendDingTalkTask.
"""

from . import client, task
from .client import DingTalkClient, DingTalkMessageType, send_dingtalk_message
from .task import (
    DingTalkInputParams,
    DingTalkOutputParams,
    SendDingTalkTask,
)

__all__ = [
    "DingTalkClient",
    "DingTalkInputParams",
    "DingTalkMessageType",
    "DingTalkOutputParams",
    "SendDingTalkTask",
    "client",
    "send_dingtalk_message",
    "task",
]
