"""Public utility helpers with lazy imports for optional dependencies."""

from typing import TYPE_CHECKING

from .env_utils import EnvLoader, load_env, parse_env_file
from .logger_utils import LoggerManager, LoggingConfig, get_logger

if TYPE_CHECKING:
    from .dingtalk_utils import DingTalkMessageType, send_dingtalk_message
    from .tushare_client import TushareClient

__all__ = [
    "DingTalkMessageType",
    "EnvLoader",
    "LoggerManager",
    "LoggingConfig",
    "TushareClient",
    "get_logger",
    "load_env",
    "parse_env_file",
    "send_dingtalk_message",
]


def __getattr__(name: str):
    """Load utilities with third-party dependencies only when requested."""
    if name == "TushareClient":
        from .tushare_client import TushareClient

        value = TushareClient
    elif name in {"DingTalkMessageType", "send_dingtalk_message"}:
        from .dingtalk_utils import DingTalkMessageType, send_dingtalk_message

        value = {
            "DingTalkMessageType": DingTalkMessageType,
            "send_dingtalk_message": send_dingtalk_message,
        }[name]
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value
