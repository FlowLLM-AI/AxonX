"""Build, inspect, and install plugin wheels."""

import configparser
import subprocess
import sys
from email.parser import Parser
from importlib import invalidate_caches
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from ..config import JobConfig
from ..constants import PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST
from ..utils.fs import directory_sha256, file_sha256
from .identity import content_sha256_from_wheel
from .manifest import parse_plugin_manifest
from .models import PluginArtifact

# ".git"/".venv"/"__pycache__" are skipped wherever they appear; "/build" and
# "/dist" only at the project root, where setuptools writes them, so a plugin
# that keeps source under a directory of the same name still hashes.
_IGNORED_PARTS = {".git", ".venv", "__pycache__", "/build", "/dist", "*.egg-info"}


def source_sha256(path: Path) -> str:
    """Hash stable source paths and contents, excluding generated files."""
    root = path.expanduser().resolve()
    if not (root / "pyproject.toml").is_file():
        raise FileNotFoundError(f"Plugin pyproject.toml not found: {root}")
    return directory_sha256(root, ignored_parts=_IGNORED_PARTS)


def build_wheel(source: Path, output: Path, *, use_cache: bool = False) -> Path:
    """Build exactly one wheel from a Python project using this interpreter.

    ``use_cache`` reuses an existing wheel when ``output`` holds exactly one. It
    does not check that the wheel matches ``source``, so an output directory must
    be keyed by the source revision — as every caller does by building under
    ``artifacts/<source digest>``.
    """
    output.mkdir(parents=True, exist_ok=True)
    existing = list(output.glob("*.whl"))
    if use_cache and len(existing) == 1:
        return existing[0]
    with TemporaryDirectory(prefix=".build-", dir=output) as temporary:
        build_output = Path(temporary)
        command = [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(build_output),
            str(source),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        wheels = list(build_output.glob("*.whl"))
        if result.returncode or len(wheels) != 1:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Plugin wheel build failed: {detail}")
        return wheels[0].replace(output / wheels[0].name)


def inspect_wheel(path: Path) -> PluginArtifact:
    """Read distribution, entry points, and manifests without importing code.

    A malformed wheel is a bad artifact, not a service fault, so every way the
    archive formats can fail is reported as a ``ValueError`` naming the file.
    ``zipfile`` and ``configparser`` raise types of their own, and letting those
    through would answer a corrupt upload with a 500 — or, on the CLI, with a
    traceback — where both callers handle a ``ValueError``.
    """
    try:
        return _read_artifact(path)
    except (BadZipFile, configparser.Error, UnicodeDecodeError) as exc:
        raise ValueError(f"Not a readable plugin wheel: {path.name}: {exc}") from exc


def _read_artifact(path: Path) -> PluginArtifact:
    with ZipFile(path) as archive:
        names = archive.namelist()
        metadata_files = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        entry_files = [
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        ]
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
        plugin_packages = {}
        for plugin_name, package in entries.items(PLUGIN_ENTRY_POINT_GROUP):
            if ":" in package:
                raise ValueError("Plugin entry point must target a package")
            manifest_path = f"{package.replace('.', '/')}/{PLUGIN_MANIFEST}"
            if manifest_path not in names:
                raise ValueError(f"Wheel does not contain {manifest_path}")
            manifest = parse_plugin_manifest(
                archive.read(manifest_path).decode(), plugin_name
            )
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
                    duplicates = ", ".join(sorted(duplicate_backends))
                    raise ValueError(
                        f"Duplicate Component backends in wheel for {component_type!r}: {duplicates}",
                    )
                registered.update(backends)
            duplicate_jobs = jobs.keys() & manifest.jobs.keys()
            if duplicate_jobs:
                raise ValueError(
                    f"Duplicate Job names in wheel: {', '.join(sorted(duplicate_jobs))}",
                )
            jobs.update(manifest.jobs)
            plugin_names.append(plugin_name)
            plugin_packages[plugin_name] = package

        distribution = metadata.get("Name")
        version = metadata.get("Version")
        if not distribution or not version:
            raise ValueError("Wheel metadata must contain Name and Version")
        requirements = tuple(metadata.get_all("Requires-Dist") or ())
        content_sha256 = content_sha256_from_wheel(
            archive,
            distribution=distribution,
            version=version,
            requirements=requirements,
            plugins=plugin_packages,
        )

    return PluginArtifact(
        distribution=distribution,
        version=version,
        plugin_names=tuple(plugin_names),
        tasks=tasks,
        requirements=requirements,
        wheel=path,
        content_sha256=content_sha256,
        sha256=file_sha256(path),
        components=components,
        jobs=jobs,
    )


def install_artifact(artifact: PluginArtifact) -> None:
    """Install plugin dependencies without replacing AxonX, then install its wheel."""
    dependencies = [
        value
        for value in artifact.requirements
        if canonicalize_name(Requirement(value).name) != "axonx"
    ]
    commands = []
    if dependencies:
        commands.append([sys.executable, "-m", "pip", "install", *dependencies])
    commands.append(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            str(artifact.wheel),
        ],
    )
    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(
                f"Plugin installation failed: {(result.stderr or result.stdout).strip()}",
            )
    invalidate_caches()
