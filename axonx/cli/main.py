"""Route one CLI invocation and translate failures into process exit codes."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence

from ..client.config import AXONX_CLI_REQUEST_ID
from .commands import LOCAL_HANDLERS
from .parser import CLI_USAGE, parse_command


def main(argv: Sequence[str] | None = None) -> int:
    """Run one AxonX command and return its process exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args in (["--help"], ["-h"]):
        print(CLI_USAGE)
        return 0
    try:
        command, client_options = parse_command(args)
        if os.environ.get(AXONX_CLI_REQUEST_ID) and (
            command.action in {"app", "cli"} or client_options.target is not None
        ):
            raise ValueError("Remote CLI cannot start a service or forward to another target")
        if client_options.target is None and (handler := LOCAL_HANDLERS.get(command.action)) is not None:
            return handler(command, client_options)
        from .remote import run_remote

        return asyncio.run(run_remote(command, client_options))
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit codes.
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError)) else 1
