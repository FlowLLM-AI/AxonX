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
)
from ..schema import Command, HttpClientOptions

_OPTION_RE = re.compile(
    r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$",
)


class CommandParser:
    """Turn command-line tokens into a validated :class:`Command`."""

    def __init__(self, argv: Sequence[str]) -> None:
        self._remaining = list(argv)

    def parse(self) -> Command:
        """Parse client options, the action, and action-specific arguments."""
        client, client_options_supplied = self._parse_client_options()
        action = self._parse_action(client_options_supplied)

        if action in CLI_PASSTHROUGH_COMMANDS:
            return Command(
                action=action,
                client=client,
                passthrough=tuple(self._remaining),
            )

        return Command(
            action=action,
            arguments=self._parse_arguments(),
            client=client,
        )

    def _parse_action(self, client_options_supplied: bool) -> str:
        """Read the command action, defaulting an empty command line to help."""
        if not self._remaining:
            if client_options_supplied:
                raise ValueError("Missing command after client options")
            return "help"

        raw_action = self._remaining.pop(0)
        action = "help" if raw_action in {"-h", "--help"} else raw_action
        if client_options_supplied and action in CLI_LOCAL_COMMANDS:
            raise ValueError(f"Client options cannot be used with local command: {action}")
        return action

    def _parse_client_options(self) -> tuple[HttpClientOptions, bool]:
        values: dict[str, Any] = {}
        while self._remaining:
            option = self._remaining[0]
            if not option.startswith("--"):
                break

            key = option[2:].replace("-", "_")
            if key not in CLI_CLIENT_OPTIONS:
                break

            self._remaining.pop(0)
            if not self._remaining or self._remaining[0].startswith("--"):
                raise ValueError(f"Missing value for client option: {option}")

            if key in values:
                raise ValueError(f"Duplicate client option: {option}")
            values[key] = convert_value(self._remaining.pop(0))

        return HttpClientOptions.model_validate(values), bool(values)

    def _parse_arguments(self) -> dict[str, Any]:
        if len(self._remaining) % 2:
            raise ValueError("Options must be pairs like --field value")

        arguments: dict[str, Any] = {}
        while self._remaining:
            option = self._remaining.pop(0)
            raw_value = self._remaining.pop(0)
            if raw_value.startswith("--"):
                raise ValueError(f"Missing value for option: {option}")
            path = self._option_path(option)
            value = convert_value(raw_value)
            self._assign_nested_value(arguments, path, value)
        return arguments

    @staticmethod
    def _option_path(option: str) -> list[str]:
        if not _OPTION_RE.fullmatch(option):
            raise ValueError(f"Invalid option: {option!r}; expected --field value")
        return [part.replace("-", "_") for part in option[2:].split(".")]

    @staticmethod
    def _assign_nested_value(
            arguments: dict[str, Any],
            path: list[str],
            value: Any,
    ) -> None:
        """Assign a value to a possibly dotted option path."""
        current = arguments
        dotted = ".".join(path)
        for key in path[:-1]:
            if key in current and not isinstance(current[key], dict):
                raise ValueError(
                    f"Cannot set nested option '{dotted}': '{key}' is already a value",
                )
            current = current.setdefault(key, {})

        final = path[-1]
        if final in current:
            raise ValueError(f"Duplicate or conflicting option: --{dotted}")
        current[final] = value


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def print_json(value: Any) -> None:
    """Print one CLI value as readable JSON."""
    print(json.dumps(value, ensure_ascii=False, default=_json_default))


def pop_required_string(
        arguments: dict[str, Any],
        name: str,
) -> tuple[str, dict[str, Any]]:
    """Copy arguments and remove one required, non-empty string option."""
    remaining = dict(arguments)
    option = f"--{name.replace('_', '-')}"
    try:
        value = remaining.pop(name)
    except KeyError:
        raise ValueError(f"Missing required option: {option}") from None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{option} must be a non-empty string")
    return value, remaining
