"""Application configuration selection over the shared loading engine."""

from pathlib import Path

from ...common.config import ConfigLoader
from ...common.constants import AXONX_DEFAULT_ENCODING, CONFIG_ENTRY_POINT_GROUP


class ConfigResolver(ConfigLoader):
    def __init__(self, config_dir: Path | str = Path(__file__).parent, *, encoding: str = AXONX_DEFAULT_ENCODING):
        super().__init__(config_dir, group=CONFIG_ENTRY_POINT_GROUP, encoding=encoding)


def resolve_app_config(*, log_config: bool = True, **overrides) -> dict:
    return ConfigResolver().resolve(log_config=log_config, **overrides)
