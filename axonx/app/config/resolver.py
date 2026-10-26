"""Resolve application configuration from bundled or installed resources."""

from pathlib import Path

from ..constants import CONFIG_ENTRY_POINT_GROUP
from .loader import ConfigLoader


def resolve_app_config(*, log_config: bool = True, **overrides) -> dict:
    return ConfigLoader(Path(__file__).parent, group=CONFIG_ENTRY_POINT_GROUP).resolve(
        log_config=log_config, **overrides
    )
