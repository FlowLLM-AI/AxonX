"""Executable command parsing; raw argv is separate from business arguments."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..utils.values import convert_value
from .arguments import TRANSPORT_OPTION_NAMES, parse_arguments
from .options import ClientOptions

_ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class Command:
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: tuple[str, ...] = ()

    def __post_init__(self):
        if not _ACTION_RE.fullmatch(self.action):
            raise ValueError(f"Invalid command action: {self.action!r}")


def parse_command(argv: Sequence[str]) -> tuple[Command, ClientOptions]:
    if not argv:
        return Command("help"), ClientOptions()
    remaining, connection = _extract_client_options(tuple(argv))
    if not remaining:
        raise ValueError("Missing command after client options")
    action, raw = remaining[0], remaining[1:]
    client = ClientOptions.model_validate(connection)
    arguments = {} if client.target is not None or action == "plugin" else parse_arguments(raw)
    return Command(action, arguments, raw), client


def validate_cron_command(argv: Sequence[str]) -> None:
    """Validate scheduled local exec commands with the same parser as the CLI."""
    if tuple(argv[:2]) != ("axonx", "exec"):
        raise ValueError("Only axonx exec --task NAME is supported")
    command, client = parse_command(argv[1:])
    if client.model_fields_set:
        raise ValueError("Client options are not supported in cron")
    task = command.arguments.get("task")
    if not isinstance(task, str) or not task:
        raise ValueError("A cron command requires --task NAME")


def _extract_client_options(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Separate connection options without interpreting command arguments."""
    client_names = TRANSPORT_OPTION_NAMES
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
