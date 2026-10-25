"""Plugin CLI for the current Python environment."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .rendering import print_json
from ..plugin.discovery import get_installed_plugin, list_installed_plugins
from ..plugin.installer import install_plugin, prepare_artifact, uninstall_plugin


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "contributions_dict"):
        return {
            "distribution": value.distribution,
            "version": value.version,
            "plugins": list(value.plugin_names),
            **value.contributions_dict(),
            "requirements": list(value.requirements),
            "wheel": str(value.wheel),
            "content_sha256": value.content_sha256,
            "sha256": value.sha256,
        }
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _run_local(args):
    if args.command == "list":
        return list_installed_plugins()
    if args.command == "show":
        return get_installed_plugin(args.plugin)
    if args.command == "inspect":
        path = Path(args.plugin).expanduser()
        return prepare_artifact(args.plugin, output=args.output) if path.exists() else get_installed_plugin(args.plugin)
    if args.command == "install":
        source = Path(args.plugin).expanduser().resolve() if args.editable else None
        if source is not None and not source.is_dir():
            raise ValueError(f"Editable plugin path must be a project directory: {source}")
        return install_plugin(prepare_artifact(args.plugin, output=args.output), editable_source=source)
    if args.command == "uninstall":
        return uninstall_plugin(args.plugin)
    raise ValueError(f"Unknown plugin command: {args.command!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axonx plugin",
        description="Manage plugins in the current Python environment.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List installed plugins.")
    for name, help_text in (
        ("show", "Show one installed plugin."),
        ("inspect", "Inspect an installed plugin, wheel, or source tree."),
        ("build", "Build and inspect a plugin wheel locally."),
        ("install", "Install a plugin locally or on the target service."),
        ("uninstall", "Uninstall a plugin locally or on the target service."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("plugin")
        if name == "install":
            command.add_argument(
                "-e",
                "--editable",
                action="store_true",
                help="Install a local source directory in editable mode.",
            )
        if name in {"inspect", "build", "install"}:
            command.add_argument("--output", help="Wheel output directory.")
    return parser


def plugin_cli(argv: Sequence[str]) -> int:
    """Run one plugin command and return its process exit status."""
    args = _parser().parse_args(list(argv))
    try:
        if args.command == "install" and args.editable and args.output is not None:
            raise ValueError("--editable cannot be combined with --output")
        if args.command == "build":
            result = prepare_artifact(args.plugin, output=args.output)
        else:
            result = _run_local(args)
        print_json(_json_value(result))
        return 0
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
