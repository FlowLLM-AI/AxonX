"""CLI grammar, connection options, plugin subcommands and offline help."""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ..client.config import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_DEFAULT_REQUEST_TIMEOUT,
    ConnectionOptions,
)
from ..utils.values import convert_value

_ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_OPTION_RE = re.compile(r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")
_CLIENT_OPTIONS = {
    "target": "target",
    "client_timeout": "timeout",
    "token": "token",
    "stream": "stream",
    "stream_format": "stream_format",
}

CLI_USAGE = f"""Usage:
  axonx [--help|-h]
  axonx help [--job NAME] [--target HOST:PORT]
  axonx diagnose [--target HOST:PORT]
  axonx JOB [--field value ...] [--client-timeout SECONDS] [--token TOKEN] [--stream true]
        [--stream-format blocks|json] [--target HOST:PORT]
  axonx wait_task --task-id ID [--client-timeout SECONDS]
  axonx list_task_defs [--include-schemas true|false] [--target HOST:PORT]
  axonx get_task_def --task NAME [--target HOST:PORT]
  axonx get_config [--target HOST:PORT]
  axonx exec [--task TASK] [--workspace-dir PATH] [--field value ...] [--target HOST:PORT]
  axonx kill --task-id ID [--workspace-dir PATH] [--timeout SECONDS] [--force true] [--target HOST:PORT]
  axonx app [--config NAME_OR_PATH]
  axonx plugin list|show|inspect|install|uninstall ... [--target HOST:PORT]
  axonx plugin build SOURCE [--workspace-dir PATH] [--output DIRECTORY] [--target HOST:PORT]
  axonx plugin install -e SOURCE

--help and -h show offline CLI usage; help queries the selected service's Jobs.
Job commands require a running service; Task definitions describe its Python environment.
exec and kill share --workspace-dir, --log-dir, --timezone, --execution-target,
--log-to-console, --log-to-file and --environment.KEY options.
Execution settings: CLI options > service get_config Job > built-in defaults.

Service options: target={AXONX_DEFAULT_CONNECT_HOST}:{AXONX_DEFAULT_PORT}
client_timeout={AXONX_DEFAULT_REQUEST_TIMEOUT:g} token=null stream=false stream_format=blocks"""


class ClientOptions(ConnectionOptions):
    """Connection and presentation options, separate from command inputs."""

    stream: bool = False
    stream_format: Literal["blocks", "json"] = "blocks"

    def connection(self) -> dict[str, Any]:
        """Resolve CLI credentials without changing library client defaults."""
        options = self.model_dump(exclude={"stream", "stream_format"})
        if self.token is None:
            key = "AXONX_TARGET_TOKEN" if self.target is not None else "AXONX_SERVICE_TOKEN"
            options["token"] = os.environ.get(key) or None
        return options


@dataclass(frozen=True, slots=True)
class Command:
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: tuple[str, ...] = ()

    def __post_init__(self):
        if not _ACTION_RE.fullmatch(self.action):
            raise ValueError(f"Invalid command action: {self.action!r}")


def parse_command(argv: Sequence[str]) -> tuple[Command, ClientOptions]:
    remaining, connection = _extract_client_options(tuple(argv))
    if not remaining:
        raise ValueError("Missing command")
    action, raw = remaining[0], remaining[1:]
    client = ClientOptions.model_validate(connection)
    arguments = (
        {} if action == "plugin" else _parse_arguments(raw, environment_strings=action in {"app", "exec", "kill"})
    )
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
    remaining: list[str] = []
    client: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        option = tokens[index]
        name = option.removeprefix("--").replace("-", "_")
        if option.startswith("--") and name in _CLIENT_OPTIONS:
            if index + 1 == len(tokens) or tokens[index + 1].startswith("--"):
                raise ValueError(f"Missing value for client option: {option}")
            client_name = _CLIENT_OPTIONS[name]
            if client_name in client:
                raise ValueError(f"Duplicate client option: {option}")
            value = tokens[index + 1]
            client[client_name] = value if name in {"target", "token", "stream_format"} else convert_value(value)
            index += 2
        else:
            remaining.append(option)
            index += 1
    return tuple(remaining), client


def _parse_arguments(tokens: Sequence[str], *, environment_strings: bool) -> dict[str, Any]:
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
                raise ValueError(f"Cannot set nested option '{dotted}': '{key}' is already a value")
            current = current.setdefault(key, {})

        final = path[-1]
        if final in current:
            raise ValueError(f"Duplicate or conflicting option: --{dotted}")
        current[final] = (
            raw_value
            if environment_strings and len(path) == 2 and path[0] == "environment"
            else convert_value(raw_value)
        )
    return arguments


def parse_plugin_arguments(argv: Sequence[str]) -> argparse.Namespace:
    """Parse plugin subcommands with positional paths and editable installs."""
    parser = argparse.ArgumentParser(
        prog="axonx plugin", description="Manage plugins in the current Python environment."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List installed plugins.")
    for name, help_text in (
        ("show", "Show one installed plugin."),
        ("inspect", "Inspect an installed plugin, wheel, or source tree."),
        ("build", "Build and inspect a plugin wheel locally."),
        ("install", "Install a plugin in the current Python environment."),
        ("uninstall", "Uninstall a plugin from the current Python environment."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("plugin")
        if name == "install":
            command.add_argument("-e", "--editable", action="store_true", help="Install a local source directory.")
        if name in {"inspect", "build", "install"}:
            command.add_argument("--output", help="Wheel output directory.")
            command.add_argument("--workspace-dir", help="Workspace containing tmp/plugins build caches.")
    args = parser.parse_args(argv)
    if args.command == "install" and args.editable and args.output is not None:
        parser.error("--editable cannot be combined with --output")
    return args
