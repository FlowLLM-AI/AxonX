"""Local plugin CLI with optional Job-backed remote execution."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from pydantic import TypeAdapter

from ..components.client import ClientOptions, HttpClient
from .discovery import get_installed_plugin, list_installed_plugins
from .installer import install_plugin, uninstall_plugin
from .models import PluginInfo, PluginInstallResult, PluginUninstallResult
from .wheel import build_wheel, inspect_wheel, source_sha256

_DEPLOY_TIMEOUT = 300.0


def _artifact(source: str, output: str | None = None):
    """Inspect a wheel or build a source tree into the requested cache."""
    path = Path(source).expanduser().resolve()
    if path.is_file():
        if path.suffix != ".whl":
            raise ValueError(
                f"Plugin path must be a project directory or a wheel: {path}"
            )
        if output:
            raise ValueError("--output cannot be combined with an existing wheel")
        return inspect_wheel(path)
    digest = source_sha256(path)
    directory = (
        Path(output).expanduser().resolve()
        if output
        else Path(".axonx/plugins/artifacts") / digest
    )
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
            "sha256": value.sha256,
        }
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _print(value: Any) -> None:
    print(json.dumps(_json_value(value), ensure_ascii=False, indent=2))


async def _run_remote(args, options: ClientOptions):
    client_values = options.model_dump(
        exclude={"stream", "stream_format"}, exclude_none=True
    )
    if args.command == "install":
        client_values["timeout"] = max(
            float(client_values.get("timeout", 0)), _DEPLOY_TIMEOUT
        )
    async with HttpClient(**client_values) as client:
        if args.command == "list":
            response = await client.run_job("list_plugins")
            if not response.success:
                raise RuntimeError(str(response.answer))
            return TypeAdapter(list[PluginInfo]).validate_python(response.answer)
        if args.command in {"show", "inspect"}:
            response = await client.run_job("inspect_plugin", {"plugin": args.target})
            if not response.success:
                raise RuntimeError(str(response.answer))
            return PluginInfo.model_validate(response.answer)
        if args.command == "uninstall":
            response = await client.run_job("uninstall_plugin", {"plugin": args.target})
            if not response.success:
                raise RuntimeError(str(response.answer))
            return PluginUninstallResult.model_validate(response.answer)
        if args.command == "install":
            artifact = _artifact(args.target, args.output)
            copied = await client.copy_file(artifact.wheel)
            try:
                if copied.sha256 != artifact.sha256:
                    raise RuntimeError(
                        "Remote workspace copy does not match the plugin wheel"
                    )
                response = await client.run_job(
                    "install_plugin",
                    {"path": copied.path, "sha256": copied.sha256},
                )
                if not response.success:
                    raise RuntimeError(str(response.answer))
                return PluginInstallResult.model_validate(response.answer)
            finally:
                await client.discard_file(copied.path)
    raise ValueError(f"Command {args.command!r} cannot run remotely")


def _run_local(args):
    if args.command == "list":
        return list_installed_plugins()
    if args.command == "show":
        return get_installed_plugin(args.target)
    if args.command == "inspect":
        path = Path(args.target).expanduser()
        return (
            _artifact(args.target, args.output)
            if path.exists()
            else get_installed_plugin(args.target)
        )
    if args.command == "build":
        return _artifact(args.target, args.output)
    if args.command == "install":
        return install_plugin(_artifact(args.target, args.output))
    if args.command == "uninstall":
        return uninstall_plugin(args.target)
    raise ValueError(f"Unknown plugin command: {args.command!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axonx plugin",
        description="Build and manage plugins locally, or use Jobs when client options select a remote service.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "list", help="List plugins installed in the selected Python environment."
    )
    for name, help_text in (
        ("show", "Show one installed plugin."),
        ("inspect", "Inspect an installed plugin, wheel, or source tree."),
        ("build", "Build and inspect a plugin wheel locally."),
        ("install", "Install a plugin locally or on the selected remote service."),
        ("uninstall", "Uninstall a plugin locally or on the selected remote service."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("target")
        if name in {"inspect", "build", "install"}:
            command.add_argument("--output", help="Wheel output directory.")
    return parser


def plugin_cli(argv: Sequence[str], client_options: ClientOptions | None = None) -> int:
    """Run one plugin command and return its process exit status."""
    args = _parser().parse_args(list(argv))
    options = client_options or ClientOptions()
    remote = options.host_ip is not None
    try:
        if remote and args.command == "build":
            raise ValueError("plugin build is local-only")
        result = asyncio.run(_run_remote(args, options)) if remote else _run_local(args)
        _print(result)
        return 0
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
