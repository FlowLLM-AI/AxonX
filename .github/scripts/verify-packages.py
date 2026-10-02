"""Verify built distributions or their installation outside the source tree."""

import argparse
import configparser
import importlib
from email.parser import BytesParser
from importlib import metadata, resources
from pathlib import Path
import tarfile
import tomllib
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = (
    ("axonx", ROOT, "axonx", None),
    ("a158", ROOT / "plugins/a158", "axonx_alpha158", "alpha158"),
    ("a158_enhanced", ROOT / "plugins/a158_enhanced", "axonx_alpha158_enhanced", "alpha158_enhanced"),
)


def verify_distributions(dist_dir: Path) -> None:
    """Check metadata, package data, entry points, and source version consistency."""
    for directory, source, package, plugin in PACKAGES:
        project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        wheels = list((dist_dir / directory).glob("*.whl"))
        sdists = list((dist_dir / directory).glob("*.tar.gz"))
        assert len(wheels) == len(sdists) == 1, f"Expected one wheel and sdist for {project['name']}"
        required = {f"{package}/__init__.py"}
        if plugin:
            required.update({f"{package}/plugin.yaml", f"{package}/config/alpha158_demo.yaml"})
        else:
            required.update({"axonx/_version.py", "axonx/config/default.yaml", "axonx/config/remote.yaml"})
        with ZipFile(wheels[0]) as archive:
            names = set(archive.namelist())
            assert required <= names, f"Missing package files: {required - names}"
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
                assert entries["axonx.configs"][plugin] == f"{package}.config:alpha158_demo"
            else:
                assert entries["console_scripts"]["axonx"] == "axonx.cli:main"
        with tarfile.open(sdists[0]) as archive:
            names = {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}
            assert required | {"pyproject.toml"} <= names, "Missing files in sdist"
            assert not any(name.startswith(("axonx_studio/", "github-pages/")) for name in names)
            assert not any("node_modules/" in name for name in names)
        print(f"Verified distributions: {project['name']} {project['version']}")


def verify_installation() -> None:
    """Exercise imports, resources, plugin discovery, and file-based config entries."""
    for _, source, package, plugin in PACKAGES:
        project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        module = importlib.import_module(package)
        assert not Path(module.__file__).resolve().is_relative_to(ROOT), "Import resolved to source checkout"
        distribution = metadata.distribution(project["name"])
        assert distribution.version == project["version"]
        files = resources.files(package)
        if plugin:
            assert files.joinpath("plugin.yaml").is_file()
            assert files.joinpath("config/alpha158_demo.yaml").is_file()
            (entry,) = [entry for entry in distribution.entry_points if entry.group == "axonx.plugins"]
            assert entry.name == plugin
            assert entry.load().__name__ == package
        else:
            assert module.__version__ == distribution.version
            assert files.joinpath("config/default.yaml").is_file()
            assert files.joinpath("config/remote.yaml").is_file()
        print(f"Verified installation: {project['name']} {distribution.version}")

    from axonx.config import ConfigResolver  # pylint: disable=import-outside-toplevel
    from axonx.plugin_kit.discovery import get_installed_plugin  # pylint: disable=import-outside-toplevel

    for _, _, _, plugin in PACKAGES[1:]:
        info = get_installed_plugin(plugin)
        assert info.error is None, info.error
        assert info.tasks, f"Plugin {plugin} has no tasks"
        assert ConfigResolver().load(plugin), f"Plugin {plugin} config did not load"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    options = parser.parse_args()
    if options.installed:
        verify_installation()
    else:
        verify_distributions(options.dist_dir)
