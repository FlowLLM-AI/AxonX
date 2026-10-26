"""Resolve application configuration from bundled or installed resources."""

from pathlib import Path

from .loader import ConfigLoader
from ..constants import CONFIG_ENTRY_POINT_GROUP


def resolve_app_config(*, log_config: bool = True, **overrides) -> dict:
    return ConfigLoader(Path(__file__).parent, group=CONFIG_ENTRY_POINT_GROUP).resolve(
        log_config=log_config, **overrides
    )
