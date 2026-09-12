"""Command-line models, parsing, and presentation helpers."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any, Sequence

from ..config import convert_value
from ..constants import (
    CLI_CLIENT_OPTIONS,
    CLI_LOCAL_COMMANDS,
    CLI_PASSTHROUGH_COMMANDS,
    CLI_RAW_ARGUMENTS,
    REMOTE_IP_ARGUMENT,
)
from ..schema import ClientOptions, Command

_OPTION_RE = re.compile(
    r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$",
)


def parse_command(argv: Sequence[str]) -> tuple[Command, ClientOptions]:
    """Parse command-line tokens and client connection options."""
    tokens = tuple(argv)
    client, action_index = _parse_client_options(tokens)
    client_options_supplied = action_index > 0

    if action_index == len(tokens):
        if client_options_supplied:
            raise ValueError("Missing command after client options")
        return Command(action="help", arguments={CLI_RAW_ARGUMENTS: []}), client

    raw_action = tokens[action_index]
    action = "help" if raw_action in {"-h", "--help"} else raw_action
    if client_options_supplied and action in CLI_LOCAL_COMMANDS:
        raise ValueError(f"Client options cannot be used with local command: {action}")

    raw_arguments = tokens[action_index + 1:]
    arguments = {} if action in CLI_PASSTHROUGH_COMMANDS else _parse_arguments(raw_arguments)
    arguments[CLI_RAW_ARGUMENTS] = _task_arguments(raw_arguments, arguments)
    return Command(action=action, arguments=arguments), client


def _task_arguments(tokens: tuple[str, ...], arguments: dict[str, Any]) -> list[str]:
    """Keep routing arguments out of the argv passed to a submitted Task."""
    if REMOTE_IP_ARGUMENT not in arguments:
        return list(tokens)
    task_arguments = []
    for option, value in zip(tokens[::2], tokens[1::2], strict=True):
        name = option.removeprefix("--").replace("-", "_")
        if name != REMOTE_IP_ARGUMENT:
            task_arguments.extend((option, value))
    return task_arguments


def _parse_client_options(tokens: tuple[str, ...]) -> tuple[ClientOptions, int]:
    """Parse the leading client options and return the action's index."""
    values: dict[str, Any] = {}
    index = 0

    while index < len(tokens):
        option = tokens[index]
        key = option.removeprefix("--").replace("-", "_")
        if not option.startswith("--") or key not in CLI_CLIENT_OPTIONS:
            break
        if index + 1 == len(tokens) or tokens[index + 1].startswith("--"):
            raise ValueError(f"Missing value for client option: {option}")
        if key in values:
            raise ValueError(f"Duplicate client option: {option}")

        values[key] = convert_value(tokens[index + 1])
        index += 2

    return ClientOptions.model_validate(values), index


def _parse_arguments(tokens: tuple[str, ...]) -> dict[str, Any]:
    if len(tokens) % 2:
        raise ValueError("Options must be pairs like --field value")

    arguments: dict[str, Any] = {}
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


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def print_json(value: Any) -> None:
    """Print one CLI value as readable JSON."""
    print(json.dumps(value, ensure_ascii=False, default=_json_default))
