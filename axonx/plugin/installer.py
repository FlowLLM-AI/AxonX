"""Install and remove plugins while keeping wheel provenance verifiable."""

from __future__ import annotations

import subprocess
import sys
from importlib import invalidate_caches
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .discovery import get_installed_plugin
from .fingerprint import source_sha256
from .models import PluginArtifact, PluginInfo
from .wheel import build_wheel, inspect_wheel


def _pip(action: str, *arguments: str) -> None:
    result = subprocess.run([sys.executable, "-m", "pip", *arguments], check=False, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Plugin {action} failed: {(result.stderr or result.stdout).strip()}")


def prepare_artifact(
    source: Path | str,
    cache_dir: Path | str,
    *,
    output: Path | str | None = None,
) -> PluginArtifact:
    """Inspect a wheel or build and inspect a plugin project."""
    path = Path(source).expanduser().resolve()
    if path.is_file():
        if path.suffix != ".whl":
            raise ValueError(f"Plugin path must be a project directory or a wheel: {path}")
        if output is not None:
            raise ValueError("--output cannot be combined with an existing wheel")
        return inspect_wheel(path)
    directory = Path(output).expanduser().resolve() if output is not None else Path(cache_dir) / source_sha256(path)
    return inspect_wheel(build_wheel(path, directory, use_cache=output is None))


def install_plugin(artifact: PluginArtifact, *, editable_source: Path | None = None) -> PluginInfo:
    """Install a wheel or editable source and validate the installed plugin."""
    dependencies = [value for value in artifact.requirements if canonicalize_name(Requirement(value).name) != "axonx"]
    if dependencies:
        _pip("installation", "install", *dependencies)
    target = ["--editable", str(editable_source)] if editable_source is not None else [str(artifact.wheel)]
    _pip("installation", "install", "--upgrade", "--force-reinstall", "--no-deps", *target)
    invalidate_caches()
    if editable_source is None:
        installed = get_installed_plugin(artifact.distribution)
    else:
        # Editable .pth files and import hooks are loaded at interpreter startup.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from axonx.plugin.discovery import get_installed_plugin; "
                "print(get_installed_plugin(sys.argv[1]).model_dump_json())",
                artifact.distribution,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(f"Installed plugin discovery failed: {(result.stderr or result.stdout).strip()}")
        installed = PluginInfo.model_validate_json(result.stdout)
    if installed.error:
        raise RuntimeError(f"Installed plugin is invalid: {installed.error}")
    if editable_source is not None:
        return installed
    if installed.sha256 != artifact.sha256:
        raise RuntimeError(
            f"Installed plugin provenance mismatch: expected {artifact.sha256}, "
            f"got {installed.sha256 or 'missing'}",
        )
    if installed.content_sha256 != artifact.content_sha256:
        raise RuntimeError(
            f"Installed plugin content mismatch: expected {artifact.content_sha256}, "
            f"got {installed.content_sha256 or 'missing'}",
        )
    return installed


def uninstall_plugin(name: str) -> dict[str, str]:
    """Uninstall one plugin distribution from the active interpreter."""
    plugin = get_installed_plugin(name)
    _pip("uninstall", "uninstall", "--yes", plugin.distribution)
    invalidate_caches()
    return {"distribution": plugin.distribution}
