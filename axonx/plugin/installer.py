"""Install and remove plugins while keeping wheel provenance verifiable."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from packaging.utils import canonicalize_name

from .discovery import get_installed_plugin, list_installed_plugins
from .models import PluginArtifact, PluginInfo, PluginInstallResult, PluginUninstallResult
from .wheel import build_wheel, inspect_wheel, install_artifact, source_sha256


def prepare_artifact(
    source: Path | str,
    cache_dir: Path | str = ".axonx/plugins/artifacts",
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
    install_artifact(artifact, editable_source=editable_source)
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


def install_staged_plugin(
    path: Path,
    expected_sha256: str,
    artifact_directory: Path,
) -> PluginInstallResult:
    """Validate a staged wheel, retain it by digest, install it, and report the result."""
    path = Path(path)
    if path.suffix != ".whl":
        raise ValueError(f"Invalid wheel filename: {path.name!r}")
    artifact = inspect_wheel(path)
    expected = expected_sha256.lower()
    if artifact.sha256 != expected:
        raise ValueError("Wheel SHA-256 mismatch")

    destination = artifact_directory / artifact.sha256 / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = not destination.exists()
    if created:
        shutil.copyfile(path, destination)
    stored = inspect_wheel(destination)
    if stored.sha256 != artifact.sha256:
        if created:
            destination.unlink(missing_ok=True)
        raise ValueError(f"Stored plugin wheel SHA-256 mismatch: {destination}")

    previous = next(
        (
            item
            for item in list_installed_plugins()
            if canonicalize_name(item.distribution) == canonicalize_name(stored.distribution)
        ),
        None,
    )
    if previous is not None and previous.sha256 == stored.sha256 and previous.content_sha256 == stored.content_sha256:
        installed = previous
    else:
        try:
            installed = install_plugin(stored)
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
    return PluginInstallResult(**installed.model_dump())


def ensure_plugin_sources(sources: list[str], artifact_directory: Path) -> list[PluginInfo]:
    """Build configured sources and install only artifacts not already active."""
    for source in sources:
        artifact = prepare_artifact(source, artifact_directory)
        installed = next(
            (
                item
                for item in list_installed_plugins()
                if canonicalize_name(item.distribution) == canonicalize_name(artifact.distribution)
            ),
            None,
        )
        if (
            installed is None
            or installed.sha256 != artifact.sha256
            or installed.content_sha256 != artifact.content_sha256
        ):
            install_plugin(artifact)
    return list_installed_plugins()


def uninstall_plugin(name: str) -> PluginUninstallResult:
    """Uninstall one plugin distribution from the active interpreter."""
    plugin = get_installed_plugin(name)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "--yes", plugin.distribution],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"Plugin uninstall failed: {(result.stderr or result.stdout).strip()}")
    return PluginUninstallResult(distribution=plugin.distribution)
