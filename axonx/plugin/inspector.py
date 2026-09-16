"""Inspect plugin wheels without importing their code."""

import configparser
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

from ..constants import PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST
from ..schema import JobConfig
from ..utils.fs import file_sha256
from .manifest import parse_plugin_manifest
from .models import PluginArtifact


def inspect_wheel(path: Path) -> PluginArtifact:
    """Read distribution, entry points, and manifests without importing code."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        metadata_files = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_files = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(metadata_files) != 1 or len(entry_files) != 1:
            raise ValueError("Wheel must contain one METADATA and entry_points.txt")
        metadata = Parser().parsestr(archive.read(metadata_files[0]).decode())
        entries = configparser.ConfigParser()
        entries.read_string(archive.read(entry_files[0]).decode())
        if not entries.has_section(PLUGIN_ENTRY_POINT_GROUP):
            raise ValueError(f"Wheel does not provide {PLUGIN_ENTRY_POINT_GROUP}")

        tasks: dict[str, str] = {}
        components: dict[str, dict[str, str]] = {}
        jobs: dict[str, JobConfig] = {}
        plugin_names = []
        for plugin_name, package in entries.items(PLUGIN_ENTRY_POINT_GROUP):
            if ":" in package:
                raise ValueError("Plugin entry point must target a package")
            manifest_path = f"{package.replace('.', '/')}/{PLUGIN_MANIFEST}"
            if manifest_path not in names:
                raise ValueError(f"Wheel does not contain {manifest_path}")
            manifest = parse_plugin_manifest(archive.read(manifest_path).decode(), plugin_name)
            duplicate = tasks.keys() & manifest.tasks.keys()
            if duplicate:
                raise ValueError(
                    f"Duplicate Task names in wheel: {', '.join(sorted(duplicate))}",
                )
            tasks.update(manifest.tasks)
            for component_type, backends in manifest.components.items():
                registered = components.setdefault(component_type, {})
                duplicate_backends = registered.keys() & backends.keys()
                if duplicate_backends:
                    names = ", ".join(sorted(duplicate_backends))
                    raise ValueError(
                        f"Duplicate Component backends in wheel for {component_type!r}: {names}",
                    )
                registered.update(backends)
            duplicate_jobs = jobs.keys() & manifest.jobs.keys()
            if duplicate_jobs:
                raise ValueError(
                    f"Duplicate Job names in wheel: {', '.join(sorted(duplicate_jobs))}",
                )
            jobs.update(manifest.jobs)
            plugin_names.append(plugin_name)

    distribution = metadata.get("Name")
    version = metadata.get("Version")
    if not distribution or not version:
        raise ValueError("Wheel metadata must contain Name and Version")
    return PluginArtifact(
        distribution=distribution,
        version=version,
        plugin_names=tuple(plugin_names),
        tasks=tasks,
        requirements=tuple(metadata.get_all("Requires-Dist") or ()),
        wheel=path,
        sha256=file_sha256(path),
        components=components,
        jobs=jobs,
    )
