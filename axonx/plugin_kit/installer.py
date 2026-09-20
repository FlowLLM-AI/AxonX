"""Install and remove plugins while keeping wheel provenance verifiable."""

from __future__ import annotations

from importlib import invalidate_caches
from pathlib import Path
import shutil
import subprocess
import sys

from packaging.utils import canonicalize_name

from .discovery import get_installed_plugin, list_installed_plugins
from .models import (
    PluginArtifact,
    PluginInfo,
    PluginInstallResult,
    PluginUninstallResult,
)
from .wheel import build_wheel, inspect_wheel, install_artifact, source_sha256


def prepare_artifact(
    source: Path | str, output: Path, *, use_cache: bool = True
) -> PluginArtifact:
    """Inspect a wheel or build and inspect a plugin project."""
    path = Path(source).expanduser().resolve()
    if path.is_file():
        if path.suffix != ".whl":
            raise ValueError(
                f"Plugin path must be a project directory or a wheel: {path}"
            )
        return inspect_wheel(path)
    digest = source_sha256(path)
    return inspect_wheel(build_wheel(path, output / digest, use_cache=use_cache))


def install_plugin(artifact: PluginArtifact) -> PluginInfo:
    """Install an artifact and return the distribution read back from the environment."""
    install_artifact(artifact)
    installed = get_installed_plugin(artifact.distribution)
    if installed.error:
        raise RuntimeError(f"Installed plugin is invalid: {installed.error}")
    if installed.sha256 != artifact.sha256:
        raise RuntimeError(
            f"Installed plugin provenance mismatch: expected {artifact.sha256}, "
            f"got {installed.sha256 or 'missing'}",
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
            if canonicalize_name(item.distribution)
            == canonicalize_name(stored.distribution)
        ),
        None,
    )
    if previous is not None and previous.sha256 == stored.sha256:
        installed = previous
    else:
        try:
            installed = install_plugin(stored)
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
    restart_required = bool(
        installed.components
        or installed.jobs
        or (previous is not None and (previous.components or previous.jobs))
    )
    return PluginInstallResult(
        **installed.model_dump(), restart_required=restart_required
    )


def ensure_plugin_sources(
    sources: list[str], artifact_directory: Path
) -> list[PluginInfo]:
    """Build configured sources and install only artifacts not already active."""
    for source in sources:
        artifact = prepare_artifact(source, artifact_directory)
        installed = next(
            (
                item
                for item in list_installed_plugins()
                if canonicalize_name(item.distribution)
                == canonicalize_name(artifact.distribution)
            ),
            None,
        )
        if installed is None or installed.sha256 != artifact.sha256:
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
        raise RuntimeError(
            f"Plugin uninstall failed: {(result.stderr or result.stdout).strip()}"
        )
    invalidate_caches()
    return PluginUninstallResult(
        distribution=plugin.distribution,
        restart_required=bool(plugin.components or plugin.jobs),
    )
