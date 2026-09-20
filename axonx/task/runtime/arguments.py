"""Translate Task arguments between structured requests and CLI argv."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ...config import convert_value

_CONFIG_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_OPTION = re.compile(r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")


def split_task_arguments(arguments: Mapping[str, Any]) -> tuple[str, dict]:
    """Return a validated Task name and its configuration values."""
    config = dict(arguments)
    try:
        name = config.pop("task")
    except KeyError:
        raise ValueError("Missing required option: --task") from None
    if not isinstance(name, str) or not name:
        raise ValueError("--task must be a non-empty string")
    return name, config


def parse_task_argv(argv: Sequence[str]) -> tuple[str, dict]:
    """Decode Task CLI option pairs without depending on the CLI entry layer."""
    tokens = tuple(argv)
    if len(tokens) % 2:
        raise ValueError("Options must be pairs like --field value")

    arguments: dict[str, Any] = {}
    for option, raw_value in zip(tokens[::2], tokens[1::2], strict=True):
        if raw_value.startswith("--"):
            raise ValueError(f"Missing value for option: {option}")
        if not _OPTION.fullmatch(option):
            raise ValueError(f"Invalid option: {option!r}; expected --field value")

        path = tuple(part.replace("-", "_") for part in option[2:].split("."))
        dotted = ".".join(path)
        current = arguments
        for key in path[:-1]:
            if key in current and not isinstance(current[key], dict):
                raise ValueError(
                    f"Cannot set nested option '{dotted}': '{key}' is already a value",
                )
            current = current.setdefault(key, {})
        final = path[-1]
        if final in current:
            raise ValueError(f"Duplicate or conflicting option: --{dotted}")
        current[final] = convert_value(raw_value)

    return split_task_arguments(arguments)


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
