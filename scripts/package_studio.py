"""Package Studio for npm and verify its Python/npm distributions."""

import argparse
import json
import re
import runpy
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "axonx_studio"


def release_version(expected_version: str = "") -> str:
    """Read the only maintained release version and validate a release tag."""
    version = runpy.run_path(str(ROOT / "axonx/_version.py"))["__version__"]
    number = r"(?:0|[1-9]\d*)"
    assert re.fullmatch(
        rf"{number}\.{number}\.{number}(?:-(?:alpha|beta|rc)\.{number})?", version
    ), "Use X.Y.Z or X.Y.Z-{alpha,beta,rc}.N for the shared Python/npm version"
    if expected_version:
        assert version == expected_version.removeprefix("v"), "Release version mismatch"
    return version


def pack_npm(destination: Path, version: str) -> None:
    """Stamp a temporary npm manifest without changing the source checkout."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    package = json.loads((STUDIO / "package.json").read_text(encoding="utf-8"))
    package["version"] = version
    with tempfile.TemporaryDirectory(prefix="axonx-studio-npm-") as directory:
        stage = Path(directory)
        for name in package["files"]:
            source = STUDIO / name
            if source.is_dir():
                shutil.copytree(source, stage / name)
            else:
                shutil.copy2(source, stage / name)
        (stage / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        subprocess.run(
            ["npm", "pack", str(stage), "--ignore-scripts", "--pack-destination", str(destination)], check=True
        )


def verify_source() -> None:
    """Keep source metadata version-free; versions belong to built packages."""
    project = tomllib.loads((STUDIO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    package = json.loads((STUDIO / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((STUDIO / "package-lock.json").read_text(encoding="utf-8"))
    assert project["name"] == "axonx-studio"
    assert package["name"] == "@flowllm-ai/axonx-studio"
    assert project["dynamic"] == ["version"] and "version" not in project
    assert all("version" not in metadata for metadata in (package, lock, lock["packages"][""]))
    assert not package.get("private"), "Studio npm package must be publishable"


def verify_distributions(dist_dir: Path, version: str) -> None:
    """Ensure wheels, sdists and npm archives contain the same complete UI."""
    assets = {
        str(path.relative_to(STUDIO / "dist")): path.read_bytes()
        for path in (STUDIO / "dist").rglob("*")
        if path.is_file()
    }
    assert "index.html" in assets, "Build Studio before packaging"
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
        (metadata,) = (
            member
            for member in archive.getmembers()
            if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")
        )
        info = BytesParser().parsebytes(archive.extractfile(metadata).read())
        assert info["Name"] == "axonx-studio" and Version(info["Version"]) == Version(version)
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
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--pack-npm", type=Path)
    parser.add_argument("--expected-version", default="")
    options = parser.parse_args()
    studio_version = release_version(options.expected_version)
    verify_source()
    if options.pack_npm:
        pack_npm(options.pack_npm, studio_version)
    if options.dist_dir:
        verify_distributions(options.dist_dir, studio_version)
    if not options.pack_npm and not options.dist_dir:
        print(studio_version)
