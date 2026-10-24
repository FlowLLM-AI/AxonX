"""Pure scalar conversion and nested option parsing shared by all entry points."""

import json
import re
from collections.abc import Sequence
from typing import Any

_LEADING_ZERO_RE = re.compile(r"^-?0\d")
_OPTION_RE = re.compile(r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")


def convert_value(value: str) -> Any:
    """Convert a textual configuration value to its natural Python value."""
    value = value.strip()
    lower = value.lower()
    if lower in {"none", "null"}:
        return None
    if lower in {"true", "false"}:
        return lower == "true"

    if not _LEADING_ZERO_RE.match(value):
        for converter in (int, float):
            try:
                return converter(value)
            except ValueError:
                pass

    try:
        return json.loads(value)
    except ValueError:
        return value


def parse_arguments(tokens: Sequence[str]) -> dict:
    if len(tokens) % 2:
        raise ValueError("Options must be pairs like --field value")

    arguments: dict = {}
    for option, raw_value in zip(tokens[::2], tokens[1::2], strict=True):
        if raw_value.startswith("--"):
            raise ValueError(f"Missing value for option: {option}")
        if not _OPTION_RE.fullmatch(option):
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

    return arguments
