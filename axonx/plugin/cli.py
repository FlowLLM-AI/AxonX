"""Small CLI for Task-only plugin wheels."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Sequence

from ..components.client import HttpClient
from .artifact import build_wheel, inspect_wheel, install_artifact, source_sha256


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
                "tasks": artifact.tasks,
                "requirements": artifact.requirements,
                "wheel": str(artifact.wheel),
                "sha256": artifact.sha256,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _build(args) -> int:
    _print(_artifact(args.path, args.output))
    return 0


def _install(args) -> int:
    artifact = _artifact(args.path, args.output)
    install_artifact(artifact)
    _print(artifact)
    return 0


def _deploy(args) -> int:
    artifact = _artifact(args.path, args.output)

    async def deploy():
        async with HttpClient(url=args.url, timeout=args.timeout) as client:
            return await client.install_plugin(artifact.wheel, args.token)

    print(json.dumps(asyncio.run(deploy()), ensure_ascii=False, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axonx plugin", description="Build and install Task plugins."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("build", _build),
        ("install", _install),
        ("deploy", _deploy),
    ):
        command = commands.add_parser(name)
        command.add_argument(
            "path", help="Plugin project path containing pyproject.toml."
        )
        command.add_argument("--output", help="Wheel output directory.")
        command.set_defaults(handler=handler)
        if name == "deploy":
            command.add_argument("--url", required=True)
            command.add_argument("--timeout", type=float, default=60)
            command.add_argument("--token")
    return parser


def plugin_cli(argv: Sequence[str]) -> int:
    args = _parser().parse_args(list(argv))
    try:
        return args.handler(args)
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
