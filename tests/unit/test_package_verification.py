"""Regression tests for research-plugin distribution completeness."""

import importlib.util
from io import BytesIO
from pathlib import Path
import tarfile
from zipfile import ZipFile

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/verify-packages.py"
SPEC = importlib.util.spec_from_file_location("verify_packages", SCRIPT)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


@pytest.fixture
def plugin_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    package = source / "sample_plugin"
    (package / "config").mkdir(parents=True)
    (package / "internal").mkdir()
    (source / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "sample-plugin"',
                'version = "1.0.0"',
                "[tool.setuptools.package-data]",
                'sample_plugin = ["plugin.yaml", "config/*.yaml"]',
            ]
        ),
        encoding="utf-8",
    )
    for name, content in {
        "__init__.py": "",
        "plugin.yaml": "tasks: {}",
        "config/alpha158_demo.yaml": "value: demo",
        "config/extra.yaml": "value: extra",
        "internal/__init__.py": "",
        "internal/train.py": "def train(): return 42",
    }.items():
        (package / name).write_text(content, encoding="utf-8")
    monkeypatch.setattr(VERIFY, "PACKAGES", (("sample", source, "sample_plugin", "sample"),))
    return source


def build_archives(source, dist, archive_kind=None, changed_file=None, replacement=None):
    """Build minimal archives, optionally removing or corrupting one member."""
    directory = dist / "sample"
    directory.mkdir(parents=True)
    files = {path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    with ZipFile(directory / "sample.whl", "w") as wheel:
        for name, content in files.items():
            if archive_kind == "wheel" and name == changed_file:
                if replacement is None:
                    continue
                content = replacement
            wheel.writestr(name, content)
        wheel.writestr("sample.dist-info/METADATA", "Name: sample-plugin\nVersion: 1.0.0\n")
        wheel.writestr(
            "sample.dist-info/entry_points.txt",
            "[axonx.plugins]\nsample = sample_plugin\n"
            "[axonx.configs]\nsample = sample_plugin.config:alpha158_demo\n",
        )
    with tarfile.open(directory / "sample.tar.gz", "w:gz") as sdist:
        for name, content in files.items():
            if archive_kind == "sdist" and name == changed_file:
                if replacement is None:
                    continue
                content = replacement
            member = tarfile.TarInfo(f"sample-1.0.0/{name}")
            member.size = len(content)
            sdist.addfile(member, BytesIO(content))


def test_complete_plugin_archives_pass(plugin_source, tmp_path):
    build_archives(plugin_source, tmp_path / "dist")
    VERIFY.verify_distributions(tmp_path / "dist")


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
@pytest.mark.parametrize("name", ["internal/train.py", "config/extra.yaml"])
def test_missing_plugin_module_or_data_fails(plugin_source, tmp_path, archive_kind, name):
    build_archives(plugin_source, tmp_path / "dist", archive_kind, f"sample_plugin/{name}")
    with pytest.raises(AssertionError, match=name):
        VERIFY.verify_distributions(tmp_path / "dist")


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
@pytest.mark.parametrize("name", ["internal/train.py", "plugin.yaml"])
def test_stale_plugin_contents_fail(plugin_source, tmp_path, archive_kind, name):
    build_archives(plugin_source, tmp_path / "dist", archive_kind, f"sample_plugin/{name}", b"stale")
    with pytest.raises(AssertionError, match="differs from source"):
        VERIFY.verify_distributions(tmp_path / "dist")


def test_unmatched_package_data_pattern_fails(plugin_source):
    (plugin_source / "sample_plugin/plugin.yaml").unlink()
    with pytest.raises(AssertionError, match="pattern matches no files"):
        VERIFY.plugin_source_files(plugin_source, "sample_plugin")


def test_subpackage_and_wildcard_data_are_checked(plugin_source):
    project = plugin_source / "pyproject.toml"
    project.write_text(
        project.read_text(encoding="utf-8") + '\n"sample_plugin.internal" = ["*.json"]\n"*" = ["*.txt"]\n',
        encoding="utf-8",
    )
    (plugin_source / "sample_plugin/internal/model.json").write_text("{}", encoding="utf-8")
    (plugin_source / "sample_plugin/internal/notes.txt").write_text("notes", encoding="utf-8")
    files = VERIFY.plugin_source_files(plugin_source, "sample_plugin")
    assert files["sample_plugin/internal/model.json"] == b"{}"
    assert files["sample_plugin/internal/notes.txt"] == b"notes"
