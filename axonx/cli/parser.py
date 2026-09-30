"""Command-line models and argument parsing."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..components.client import ClientOptions
from ..config import convert_value
from ..constants import (
    CLI_CLIENT_OPTIONS,
    CLI_HELP_COMMAND,
    CLI_LOCAL_COMMANDS,
    CLI_PASSTHROUGH_COMMANDS,
    CLI_PLUGIN_COMMAND,
    CLI_RAW_ARGUMENTS,
)

_OPTION_RE = re.compile(
    r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$",
)
_ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class Command:
    """One parsed CLI command."""

    action: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ACTION_RE.fullmatch(self.action):
            raise ValueError(f"Invalid command action: {self.action!r}")


def parse_command(argv: Sequence[str]) -> tuple[Command, ClientOptions]:
    """Parse command-line tokens and client connection options."""
    tokens = tuple(argv)
    if not tokens:
        return Command(
            action=CLI_HELP_COMMAND, arguments={CLI_RAW_ARGUMENTS: []}
        ), ClientOptions()
    leading_client: dict[str, Any] = {}
    action_index = 0
    while action_index < len(tokens):
        option = tokens[action_index]
        name = option.removeprefix("--").replace("-", "_")
        if not option.startswith("--") or name not in CLI_CLIENT_OPTIONS:
            break
        if action_index + 1 == len(tokens) or tokens[action_index + 1].startswith("--"):
            raise ValueError(f"Missing value for client option: {option}")
        key = "timeout" if name == "client_timeout" else name
        if key in leading_client:
            raise ValueError(f"Duplicate client option: {option}")
        leading_client[key] = convert_value(tokens[action_index + 1])
        action_index += 2
    if action_index == len(tokens):
        raise ValueError("Missing command after client options")
    raw_action = tokens[action_index]
    action = CLI_HELP_COMMAND if raw_action in {"-h", "--help"} else raw_action
    if action in CLI_LOCAL_COMMANDS - {CLI_PLUGIN_COMMAND} and leading_client:
        raise ValueError(f"Client options cannot be used with local command: {action}")
    raw_arguments, trailing_client = _extract_trailing_client_options(
        action, tokens[action_index + 1 :]
    )
    for key in trailing_client:
        if key in leading_client:
            raise ValueError(f"Duplicate client option: --{key.replace('_', '-')}")
    client = ClientOptions.model_validate({**leading_client, **trailing_client})
    arguments = (
        {} if action in CLI_PASSTHROUGH_COMMANDS else _parse_arguments(raw_arguments)
    )
    arguments[CLI_RAW_ARGUMENTS] = list(raw_arguments)
    return Command(action=action, arguments=arguments), client


def _extract_trailing_client_options(
    action: str, tokens: tuple[str, ...]
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Take client options from a Job or plugin command."""
    if action in CLI_LOCAL_COMMANDS and action != CLI_PLUGIN_COMMAND:
        for option in ("--target", "--client-timeout"):
            if option in tokens:
                raise ValueError(f"{option} cannot be used with local command: {action}")
        return tokens, {}
    client_names = CLI_CLIENT_OPTIONS
    remaining: list[str] = []
    client: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        option = tokens[index]
        name = option.removeprefix("--").replace("-", "_")
        if option.startswith("--") and name in client_names:
            if index + 1 == len(tokens) or tokens[index + 1].startswith("--"):
                raise ValueError(f"Missing value for client option: {option}")
            client_name = "timeout" if name == "client_timeout" else name
            if client_name in client:
                raise ValueError(f"Duplicate client option: {option}")
            client[client_name] = convert_value(tokens[index + 1])
            index += 2
        else:
            remaining.append(option)
            index += 1
    return tuple(remaining), client


def _parse_arguments(tokens: tuple[str, ...]) -> dict:
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
