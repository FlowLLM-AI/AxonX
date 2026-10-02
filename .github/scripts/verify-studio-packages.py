"""Verify Studio versions and identical static assets across distributions."""

import argparse
from email.parser import BytesParser
import json
from pathlib import Path
import tarfile
import tomllib
from zipfile import ZipFile

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / "axonx_studio"


def verify_versions(expected_version: str | None) -> None:
    """Require a single source version for both package registries."""
    project = tomllib.loads((STUDIO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    package = json.loads((STUDIO / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((STUDIO / "package-lock.json").read_text(encoding="utf-8"))
    assert project["name"] == "axonx-studio"
    assert package["name"] == "@flowllm-ai/axonx-studio"
    assert project["version"] == package["version"] == lock["version"] == lock["packages"][""]["version"]
    if expected_version:
        assert package["version"] == expected_version, "Studio release version mismatch"
    assert not package.get("private"), "Studio npm package must be publishable"


def verify_distributions(dist_dir: Path) -> None:
    """Ensure wheels, sdists and npm archives contain the same complete UI."""
    assets = {
        str(path.relative_to(STUDIO / "dist")): path.read_bytes()
        for path in (STUDIO / "dist").rglob("*")
        if path.is_file()
    }
    assert "index.html" in assets, "Build Studio before packaging"
    version = json.loads((STUDIO / "package.json").read_text(encoding="utf-8"))["version"]
    (wheel,) = (dist_dir / "python").glob("*.whl")
    (sdist,) = (dist_dir / "python").glob("*.tar.gz")
    (npm,) = (dist_dir / "npm").glob("*.tgz")
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "axonx_studio/__init__.py" in names
        (metadata,) = (name for name in names if name.endswith(".dist-info/METADATA"))
        info = BytesParser().parsebytes(archive.read(metadata))
        assert info["Name"] == "axonx-studio"
        assert Version(info["Version"]) == Version(version)
        actual = {
            name.removeprefix("axonx_studio/dist/"): archive.read(name)
            for name in names
            if name.startswith("axonx_studio/dist/") and not name.endswith("/")
        }
        assert actual == assets, "Wheel static assets differ from the build"
        assert not any(name.startswith("axonx_studio/src/") for name in names)
    with tarfile.open(sdist) as archive:
        actual = {
            member.name.split("/dist/", 1)[1]: archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile() and "/dist/" in member.name
        }
        assert actual == assets, "Sdist static assets differ from the build"
    with tarfile.open(npm) as archive:
        actual = {
            member.name.removeprefix("package/dist/"): archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile() and member.name.startswith("package/dist/")
        }
        assert actual == assets, "npm static assets differ from the build"
        package = json.load(archive.extractfile("package/package.json"))
        assert package["name"] == "@flowllm-ai/axonx-studio" and package["version"] == version
    print(f"Verified Studio {version}: Python and npm contain identical static assets")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version")
    parser.add_argument("--dist-dir", type=Path)
    options = parser.parse_args()
    verify_versions(options.expected_version)
    if options.dist_dir:
        verify_distributions(options.dist_dir)
