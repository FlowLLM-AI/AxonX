"""Plugin CLI for the current Python environment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .discovery import get_installed_plugin, list_installed_plugins
from .installer import install_plugin, uninstall_plugin
from .wheel import build_wheel, inspect_wheel, source_sha256


def _artifact(source: str, output: str | None = None):
    """Inspect a wheel or build a source tree into the requested cache."""
    path = Path(source).expanduser().resolve()
    if path.is_file():
        if path.suffix != ".whl":
            raise ValueError(f"Plugin path must be a project directory or a wheel: {path}")
        if output:
            raise ValueError("--output cannot be combined with an existing wheel")
        return inspect_wheel(path)
    digest = source_sha256(path)
    directory = Path(output).expanduser().resolve() if output else Path(".axonx/plugins/artifacts") / digest
    return inspect_wheel(build_wheel(path, directory, use_cache=output is None))


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


def _print(value: Any) -> None:
    print(json.dumps(_json_value(value), ensure_ascii=False, indent=2))


def _run_local(args):
    if args.command == "list":
        return list_installed_plugins()
    if args.command == "show":
        return get_installed_plugin(args.plugin)
    if args.command == "inspect":
        path = Path(args.plugin).expanduser()
        return _artifact(args.plugin, args.output) if path.exists() else get_installed_plugin(args.plugin)
    if args.command == "install":
        source = Path(args.plugin).expanduser().resolve() if args.editable else None
        if source is not None and not source.is_dir():
            raise ValueError(f"Editable plugin path must be a project directory: {source}")
        return install_plugin(_artifact(args.plugin, args.output), editable_source=source)
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
            result = _artifact(args.plugin, args.output)
        else:
            result = _run_local(args)
        _print(result)
        return 0
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
