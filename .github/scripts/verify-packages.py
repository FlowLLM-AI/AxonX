"""Verify built distributions or their installation outside the source tree."""

import argparse
import configparser
import importlib
from email.parser import BytesParser
from importlib import metadata, resources
from pathlib import Path
import runpy
import tarfile
import tomllib
from zipfile import ZipFile

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = (
    ("axonx", ROOT, "axonx", None),
    ("qlib_a158", ROOT / "plugins/qlib_a158", "axonx_qlib_a158", "qlib_a158"),
    ("qlib_factor", ROOT / "plugins/qlib_factor", "axonx_qlib_factor", "qlib_factor"),
    ("qlib_strategy", ROOT / "plugins/qlib_strategy", "axonx_qlib_strategy", "qlib_strategy"),
)


def read_project(source: Path) -> dict:
    """Read project metadata, resolving AxonX's source-tree version."""
    config = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    if "version" in project.get("dynamic", []):
        assert config["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "axonx._version.VERSION"
        project["version"] = runpy.run_path(str(source / "axonx/_version.py"))["VERSION"]
    return project


def plugin_source_files(source: Path, package: str) -> dict[str, bytes]:
    """Derive plugin modules and declared package data from the source tree."""
    package_root = source / package
    config = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = config["tool"]["setuptools"].get("package-data", {})
    files = set(package_root.rglob("*.py"))
    package_dirs = {package_root, *(path.parent for path in files if path.name == "__init__.py")}
    for name, patterns in package_data.items():
        roots = package_dirs if name == "*" else {source / name.replace(".", "/")}
        for pattern in patterns:
            matches = {path for root in roots for path in root.glob(pattern) if path.is_file()}
            assert matches, f"Package data pattern matches no files: {name}: {pattern}"
            files.update(matches)
    return {path.relative_to(source).as_posix(): path.read_bytes() for path in sorted(files)}


def verify_distributions(dist_dir: Path, expected_version: str | None = None) -> None:
    """Check metadata, package data, entry points, and source version consistency."""
    for directory, source, package, plugin in PACKAGES:
        project = read_project(source)
        if directory == "axonx" and expected_version:
            assert Version(project["version"]) == Version(
                expected_version.removeprefix("v")
            ), "Release version mismatch"
        wheels = list((dist_dir / directory).glob("*.whl"))
        sdists = list((dist_dir / directory).glob("*.tar.gz"))
        assert len(wheels) == len(sdists) == 1, f"Expected one wheel and sdist for {project['name']}"
        required = {f"{package}/__init__.py"}
        source_files = plugin_source_files(source, package)
        required.update(source_files)
        if plugin:
            required.add(f"{package}/plugin.yaml")
        else:
            required.update({"axonx/_version.py", "axonx/config/default.yaml", "axonx/config/remote.yaml"})
        with ZipFile(wheels[0]) as archive:
            names = set(archive.namelist())
            assert required <= names, f"Missing package files: {required - names}"
            for name, content in source_files.items():
                assert archive.read(name) == content, f"Wheel file differs from source: {name}"
            assert not any(name.startswith(("tests/", "axonx_studio/", "github-pages/")) for name in names)
            assert not any("node_modules/" in name for name in names)
            (metadata_file,) = [name for name in names if name.endswith(".dist-info/METADATA")]
            info = BytesParser().parsebytes(archive.read(metadata_file))
            assert info["Name"] == project["name"]
            assert info["Version"] == project["version"]
            (entries_file,) = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
            entries = configparser.ConfigParser()
            entries.read_string(archive.read(entries_file).decode("utf-8"))
            if plugin:
                assert entries["axonx.plugins"][plugin] == package
                if "axonx.configs" in project.get("entry-points", {}):
                    assert entries["axonx.configs"][plugin] == project["entry-points"]["axonx.configs"][plugin]
            else:
                assert entries["console_scripts"]["axonx"] == "axonx.cli:main"
        with tarfile.open(sdists[0]) as archive:
            members = {
                member.name.split("/", 1)[1]: member
                for member in archive.getmembers()
                if member.isfile() and "/" in member.name
            }
            names = set(members)
            missing = (required | {"pyproject.toml"}) - names
            assert not missing, f"Missing files in sdist: {missing}"
            for name, content in source_files.items():
                assert archive.extractfile(members[name]).read() == content, f"Sdist file differs from source: {name}"
            assert not any(name.startswith(("axonx_studio/", "github-pages/")) for name in names)
            assert not any("node_modules/" in name for name in names)
        print(f"Verified distributions: {project['name']} {project['version']}")


def verify_installation() -> None:
    """Exercise imports, resources, plugin discovery, and file-based config entries."""
    for _, source, package, plugin in PACKAGES:
        project = read_project(source)
        module = importlib.import_module(package)
        assert not Path(module.__file__).resolve().is_relative_to(ROOT), "Import resolved to source checkout"
        distribution = metadata.distribution(project["name"])
        assert distribution.version == project["version"]
        files = resources.files(package)
        if plugin:
            assert files.joinpath("plugin.yaml").is_file()
            if "axonx.configs" in project.get("entry-points", {}):
                config_name = project["entry-points"]["axonx.configs"][plugin].split(":")[1]
                assert files.joinpath(f"config/{config_name}.yaml").is_file()
            (entry,) = [entry for entry in distribution.entry_points if entry.group == "axonx.plugins"]
            assert entry.name == plugin
            assert entry.load().__name__ == package
        else:
            assert module.__version__ == distribution.version
            assert files.joinpath("config/default.yaml").is_file()
            assert files.joinpath("config/remote.yaml").is_file()
            for language in ("en", "zh"):
                guide = files.joinpath("components/agent/guides", f"{language}.md")
                assert guide.read_bytes() == (source / "docs" / language / "dev_guide.md").read_bytes()
        print(f"Verified installation: {project['name']} {distribution.version}")

    from axonx.config import ConfigResolver  # pylint: disable=import-outside-toplevel
    from axonx.plugin_kit.discovery import get_installed_plugin  # pylint: disable=import-outside-toplevel

    for _, source, _, plugin in PACKAGES[1:]:
        info = get_installed_plugin(plugin)
        assert info.error is None, info.error
        assert info.tasks, f"Plugin {plugin} has no tasks"
        if "axonx.configs" in read_project(source).get("entry-points", {}):
            assert ConfigResolver().load(plugin), f"Plugin {plugin} config did not load"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version")
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    options = parser.parse_args()
    if options.installed:
        verify_installation()
    else:
        verify_distributions(options.dist_dir, options.expected_version)
