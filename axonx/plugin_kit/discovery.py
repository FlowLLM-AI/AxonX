"""Discover AxonX plugins from the active Python environment."""

from __future__ import annotations

from importlib import metadata
import json
from typing import Any

from packaging.utils import canonicalize_name

from ..constants import AXONX_DEFAULT_ENCODING, PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST
from .manifest import parse_plugin_manifest
from .models import PluginInfo


def _wheel_sha256(distribution: Any) -> str | None:
    """Return the wheel digest recorded by pip's direct-url metadata."""
    direct_url = distribution.read_text("direct_url.json")
    if not direct_url:
        return None
    try:
        provenance = json.loads(direct_url)
    except (TypeError, json.JSONDecodeError):
        return None
    archive = provenance.get("archive_info", {})
    digest = archive.get("hashes", {}).get("sha256")
    if isinstance(digest, str) and digest:
        return digest.lower()
    legacy = archive.get("hash")
    if isinstance(legacy, str) and legacy.startswith("sha256="):
        return legacy.removeprefix("sha256=").lower()
    return None


def _distribution_info(distribution: metadata.Distribution) -> PluginInfo | None:
    entries = [
        entry
        for entry in distribution.entry_points
        if entry.group == PLUGIN_ENTRY_POINT_GROUP
    ]
    if not entries:
        return None

    tasks: dict[str, str] = {}
    components: dict[str, dict[str, str]] = {}
    jobs = {}
    plugin_names: list[str] = []
    for entry in entries:
        package = entry.value
        if ":" in package:
            raise ValueError(f"Plugin entry point {entry.name!r} must target a package")
        manifest_path = distribution.locate_file(
            f"{package.replace('.', '/')}/{PLUGIN_MANIFEST}"
        )
        if not manifest_path.is_file():
            raise ValueError(
                f"Plugin {entry.name!r} does not contain {PLUGIN_MANIFEST}"
            )
        manifest = parse_plugin_manifest(
            manifest_path.read_text(encoding=AXONX_DEFAULT_ENCODING), entry.name
        )

        duplicate_tasks = tasks.keys() & manifest.tasks.keys()
        if duplicate_tasks:
            raise ValueError(
                f"Duplicate Task names in distribution: {', '.join(sorted(duplicate_tasks))}"
            )
        tasks.update(manifest.tasks)
        for component_type, backends in manifest.components.items():
            registered = components.setdefault(component_type, {})
            duplicates = registered.keys() & backends.keys()
            if duplicates:
                raise ValueError(
                    f"Duplicate Component backends in distribution for {component_type!r}: "
                    f"{', '.join(sorted(duplicates))}",
                )
            registered.update(backends)
        duplicate_jobs = jobs.keys() & manifest.jobs.keys()
        if duplicate_jobs:
            raise ValueError(
                f"Duplicate Job names in distribution: {', '.join(sorted(duplicate_jobs))}"
            )
        jobs.update(manifest.jobs)
        plugin_names.append(entry.name)

    name = distribution.metadata.get("Name")
    version = distribution.version
    if not name or not version:
        raise ValueError("Installed plugin metadata must contain Name and Version")
    return PluginInfo(
        distribution=name,
        version=version,
        plugins=plugin_names,
        tasks=tasks,
        components=components,
        jobs=jobs,
        requirements=list(distribution.requires or ()),
        sha256=_wheel_sha256(distribution),
    )


def list_installed_plugins() -> list[PluginInfo]:
    """Return every AxonX plugin distribution, including broken installations."""
    found: dict[str, PluginInfo] = {}
    for distribution in metadata.distributions():
        entries = [
            entry
            for entry in distribution.entry_points
            if entry.group == PLUGIN_ENTRY_POINT_GROUP
        ]
        if not entries:
            continue
        try:
            info = _distribution_info(distribution)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            name = distribution.metadata.get("Name") or "unknown"
            info = PluginInfo(
                distribution=name,
                version=distribution.version or "unknown",
                plugins=[entry.name for entry in entries],
                requirements=list(distribution.requires or ()),
                sha256=_wheel_sha256(distribution),
                error=str(exc),
            )
        if info is None:
            continue
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


def installed_plugin_for_task(task_name: str) -> tuple[str, str | None] | None:
    """Return the installed distribution and wheel digest providing a Task."""
    matches = [info for info in list_installed_plugins() if task_name in info.tasks]
    if len(matches) > 1:
        raise ValueError(
            f"Task {task_name!r} has multiple locally installed plugin providers"
        )
    if not matches:
        return None
    return matches[0].distribution, matches[0].sha256
