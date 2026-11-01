"""Route one CLI invocation and translate failures into process exit codes."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence

from ..client.config import AXONX_CLI_REQUEST_ID
from ..utils import env
from .commands import LOCAL_HANDLERS
from .parser import CLI_USAGE, parse_command
from .remote import forward_cli, run_http, run_job


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
        if command.action == "app" and client_options.target is not None:
            raise ValueError("app only supports local service startup")
        # The daemon snapshots inherited values before loading .env so restarts can reload it.
        if command.action != "app":
            env.load_env(override=False)
        if (handler := LOCAL_HANDLERS.get(command.action)) is not None:
            if client_options.target is None:
                return handler(command, client_options)
            remote_handler = forward_cli
        elif command.action in {"upload", "upload_archive", "discard_file", "health", "list_jobs"}:
            remote_handler = run_http
        else:
            remote_handler = run_job
        return asyncio.run(remote_handler(command, client_options, client_options.connection()))
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit codes.
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError)) else 1
