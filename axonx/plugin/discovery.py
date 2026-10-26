"""Discover AxonX plugins from the active Python environment."""

from __future__ import annotations

import json
from importlib import metadata, util
from pathlib import Path

from packaging.utils import canonicalize_name

from .fingerprint import content_sha256_from_directories
from .manifest import PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST, PluginManifest
from .models import PluginInfo


def _wheel_sha256(distribution: metadata.Distribution) -> str | None:
    """Return the wheel digest recorded by pip's direct-url metadata."""
    direct_url = distribution.read_text("direct_url.json")
    if not direct_url:
        return None
    try:
        provenance = json.loads(direct_url)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(provenance, dict):
        return None
    archive = provenance.get("archive_info")
    hashes = archive.get("hashes") if isinstance(archive, dict) else None
    digest = hashes.get("sha256") if isinstance(hashes, dict) else None
    if isinstance(digest, str) and digest:
        return digest.lower()
    return None


def _package_path(distribution: metadata.Distribution, package: str) -> Path:
    """Locate a regular or editable-installed plugin package."""
    installed = Path(distribution.locate_file(package.replace(".", "/"))).resolve()
    if installed.is_dir():
        return installed
    specification = util.find_spec(package)
    locations = list(specification.submodule_search_locations or ()) if specification else []
    if len(locations) != 1:
        raise FileNotFoundError(f"Cannot locate plugin package: {package}")
    return Path(locations[0]).resolve()


def _distribution_info(distribution: metadata.Distribution, packages: dict[str, str]) -> PluginInfo:
    package_paths: dict[str, Path] = {}

    def read_manifest(package: str) -> str:
        if package not in package_paths:
            package_paths[package] = _package_path(distribution, package)
        return (package_paths[package] / PLUGIN_MANIFEST).read_text(encoding="utf-8")

    manifest = PluginManifest.from_packages(packages, read_manifest)
    name = distribution.metadata.get("Name")
    version = distribution.version
    if not name or not version:
        raise ValueError("Installed plugin metadata must contain Name and Version")
    requirements = list(distribution.requires or ())
    return PluginInfo(
        distribution=name,
        version=version,
        plugins=list(packages),
        tasks=manifest.tasks,
        requirements=requirements,
        content_sha256=content_sha256_from_directories(
            distribution=name,
            version=version,
            requirements=requirements,
            plugins=packages,
            package_paths=package_paths,
        ),
        sha256=_wheel_sha256(distribution),
    )


def list_installed_plugins() -> list[PluginInfo]:
    """Return every AxonX plugin distribution, including broken installations."""
    found: dict[str, PluginInfo] = {}
    for distribution in metadata.distributions():
        entries = [entry for entry in distribution.entry_points if entry.group == PLUGIN_ENTRY_POINT_GROUP]
        if not entries:
            continue
        try:
            packages = {entry.name: entry.value for entry in entries}
            if len(packages) != len(entries):
                raise ValueError("Duplicate plugin entry-point names in distribution")
            info = _distribution_info(distribution, packages)
        except (ImportError, OSError, UnicodeDecodeError, ValueError) as exc:
            name = distribution.metadata.get("Name") or "unknown"
            info = PluginInfo(
                distribution=name,
                version=distribution.version or "unknown",
                plugins=[entry.name for entry in entries],
                requirements=list(distribution.requires or ()),
                content_sha256=None,
                sha256=_wheel_sha256(distribution),
                error=str(exc),
            )
        key = canonicalize_name(info.distribution)
        # importlib resolves the first matching distribution on sys.path. Keep
        # that same winner when an editable checkout shadows a site-packages
        # installation, otherwise inspection would describe code Python does
        # not actually import.
        found.setdefault(key, info)
    return sorted(found.values(), key=lambda item: canonicalize_name(item.distribution))


def get_installed_plugin(name: str) -> PluginInfo:
    """Find one installed plugin by distribution or manifest entry-point name."""
    canonical = canonicalize_name(name)
    matches = [
        info
        for info in list_installed_plugins()
        if canonicalize_name(info.distribution) == canonical or name in info.plugins
    ]
    if not matches:
        raise ValueError(f"Unknown plugin: {name!r}")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous plugin: {name!r}")
    return matches[0]
