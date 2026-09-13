"""Helpers for moving Task arguments between structured and CLI forms."""

import json
from collections.abc import Mapping, Sequence
import re
from typing import Any

_CONFIG_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def split_task_arguments(arguments: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return a validated Task name and its configuration values."""
    config = dict(arguments)
    try:
        name = config.pop("task")
    except KeyError:
        raise ValueError("Missing required option: --task") from None
    if not isinstance(name, str) or not name:
        raise ValueError("--task must be a non-empty string")
    return name, config


def build_task_argv(name: str, config: Mapping[str, Any]) -> list[str]:
    """Encode structured Task arguments as lossless CLI option pairs."""
    argv = ["--task", name]
    for key, value in config.items():
        if not isinstance(key, str) or not _CONFIG_KEY.fullmatch(key):
            raise ValueError(f"Invalid Task configuration key: {key!r}")
        argv.extend((f"--{key.replace('_', '-')}", _encode_cli_value(value)))
    return argv


def task_name_from_argv(argv: Sequence[str]) -> str | None:
    """Return the value following ``--task``, when present."""
    try:
        return argv[argv.index("--task") + 1]
    except (ValueError, IndexError):
        return None


def _encode_cli_value(value: Any) -> str:
    if value is not None and not isinstance(value, (str, bool, int, float, list, dict)):
        raise TypeError(f"Unsupported Task argument type: {type(value).__name__}")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
