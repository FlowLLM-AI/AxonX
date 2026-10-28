"""Command-line entry point and command capabilities.

parser: Command grammar, connection options, plugin arguments and offline help.
commands: Local service, Task and plugin command adapters.
remote: Remote Job invocation, CLI forwarding and streamed output handling.
rendering: JSON, event blocks and terminal result formatting.
main: Public CLI entry function, command routing and process exit codes.
"""

from . import commands, parser, remote, rendering
from .main import main
from .parser import Command, parse_command

__all__ = [
    "Command",
    "commands",
    "main",
    "parse_command",
    "parser",
    "remote",
    "rendering",
]
