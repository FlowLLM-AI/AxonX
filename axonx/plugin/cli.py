"""Plugin CLI boundaries.

List, status, and inspect call JSON Jobs on the local or selected remote service.
Build and install run only in the CLI machine's Python environment.
Deploy builds locally and uploads a binary wheel to a local or remote service.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Sequence

from ..components.client import HttpClient
from . import build_wheel, inspect_wheel, install_artifact, source_sha256

_QUERY_ACTIONS = frozenset({"list", "status", "inspect"})
_CLIENT_OPTIONS = frozenset({"--host-ip", "--host-port", "--timeout"})


def plugin_job_argv(argv: Sequence[str]) -> list[str] | None:
    """Map plugin queries to Jobs on the local or selected remote service.

    Build and install stay in the CLI process. Deploy uploads a wheel through
    its binary HTTP endpoint, so those actions are not mapped to JSON Jobs.
    """
    tokens = list(argv)
    index = 0
    while index < len(tokens) and tokens[index] in _CLIENT_OPTIONS:
        index += 2
    if index + 1 >= len(tokens) or tokens[index] != "plugin":
        return None
    action = tokens[index + 1]
    if action not in _QUERY_ACTIONS:
        return None
    client = tokens[:index]
    arguments: list[str] = []
    remainder = tokens[index + 2 :]
    if "--help" in remainder or "-h" in remainder:
        return None
    if len(remainder) % 2:
        raise ValueError("Plugin query options must be pairs like --name value")
    for option, value in zip(remainder[::2], remainder[1::2], strict=True):
        (client if option in _CLIENT_OPTIONS else arguments).extend((option, value))
    return [*client, f"{action}_plugins", *arguments]


def _artifact(source: str, output: str | None = None):
    path = Path(source).expanduser().resolve()
    digest = source_sha256(path)
    if output:
        directory = Path(output).expanduser().resolve()
        return inspect_wheel(build_wheel(path, directory))
    directory = Path(".axonx/plugins/artifacts") / digest
    return inspect_wheel(build_wheel(path, directory, use_cache=True))


def _print(artifact) -> None:
    print(
        json.dumps(
            {
                "distribution": artifact.distribution,
                "version": artifact.version,
                "plugins": artifact.plugin_names,
                **artifact.contributions_dict(),
                "requirements": artifact.requirements,
                "wheel": str(artifact.wheel),
                "sha256": artifact.sha256,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def _build(args) -> int:
    """Build a wheel using only the CLI machine's filesystem."""
    _print(_artifact(args.path, args.output))
    return 0


def _install(args) -> int:
    """Install into the CLI machine's Python environment, not a service."""
    artifact = _artifact(args.path, args.output)
    install_artifact(artifact)
    _print(artifact)
    return 0


def _deploy(args) -> int:
    """Upload a locally built wheel to a local or remote AxonX service."""
    artifact = _artifact(args.path, args.output)

    async def deploy():
        async with HttpClient(host_ip=args.host_ip, host_port=args.host_port, timeout=args.timeout) as client:
            return await client.install_plugin(artifact.wheel, args.token)

    print(json.dumps(asyncio.run(deploy()), ensure_ascii=False, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axonx plugin",
        description="Build, install, deploy, and query AxonX plugins.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List plugins managed by a local or remote service.")
    queries = [listing]
    for name, description in (
        ("status", "Show saved status for a managed plugin."),
        ("inspect", "Inspect a managed plugin wheel on the service machine."),
    ):
        query = commands.add_parser(name, help=description)
        query.add_argument("--plugin", required=True, help="Distribution or manifest plugin name.")
        queries.append(query)
    for query in queries:
        query.add_argument("--host-ip", help="Service IP; defaults to the local service.")
        query.add_argument("--host-port", type=int, help="Service port; required with --host-ip.")
        query.add_argument("--timeout", type=float, help="Request timeout in seconds.")
    for name, handler, description in (
        ("build", _build, "Build a wheel on this machine."),
        ("install", _install, "Install into this machine's Python environment."),
        ("deploy", _deploy, "Upload a wheel to a local or remote service."),
    ):
        command = commands.add_parser(name, help=description)
        command.add_argument("path", help="Plugin project path containing pyproject.toml.")
        command.add_argument("--output", help="Wheel output directory.")
        command.set_defaults(handler=handler)
        if name == "deploy":
            command.add_argument("--host-ip", required=True)
            command.add_argument("--host-port", required=True, type=int)
            command.add_argument("--timeout", type=float, default=60)
            command.add_argument("--token")
    return parser


def plugin_cli(argv: Sequence[str]) -> int:
    """Run the plugin subcommand with the supplied arguments."""
    args = _parser().parse_args(list(argv))
    try:
        return args.handler(args)
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
