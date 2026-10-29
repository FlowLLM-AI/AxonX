"""Plugin contracts across wheel inspection, installation and Task resolution."""

import json
import sys
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from axonx.cli import main
from axonx.plugin import discovery, fingerprint, installer, wheel
from axonx.plugin.manifest import PluginManifest
from axonx.plugin.models import PluginInfo


def make_wheel(tmp_path, *, packages=None, compression=ZIP_STORED):
    packages = packages or {
        "ResearchPlugin": ("example_plugin", "tasks: {research: axonx.task.builtins.demo:DemoTask}")
    }
    path = tmp_path / "example_plugin-1.0-py3-none-any.whl"
    with ZipFile(path, "w", compression=compression) as archive:
        archive.writestr(
            "example_plugin-1.0.dist-info/METADATA",
            "Name: example-plugin\nVersion: 1.0\nRequires-Dist: axonx>=0.1\nRequires-Dist: packaging>=20\n",
        )
        archive.writestr(
            "example_plugin-1.0.dist-info/entry_points.txt",
            "[axonx.plugins]\n" + "\n".join(f"{name} = {package}" for name, (package, _) in packages.items()),
        )
        for package, manifest in packages.values():
            prefix = package.replace(".", "/")
            archive.writestr(
                f"{prefix}/__init__.py", "raise RuntimeError('Plugin code must not run during inspection')"
            )
            archive.writestr(f"{prefix}/plugin.yaml", manifest)
    return path


def installed_distribution(path, root, *, provenance=None):
    with ZipFile(path) as archive:
        archive.extractall(root)
    info = root / "example_plugin-1.0.dist-info"
    if provenance is not None:
        (info / "direct_url.json").write_text(provenance)
    return metadata.Distribution.at(info)


def test_wheel_and_installed_metadata_agree_without_importing_plugin_code(tmp_path, monkeypatch, capsys):
    path = make_wheel(tmp_path)
    artifact = wheel.inspect_wheel(path)
    provenance = json.dumps({"archive_info": {"hashes": {"sha256": artifact.sha256.upper()}}})
    distribution = installed_distribution(path, tmp_path / "installed", provenance=provenance)
    monkeypatch.setattr(discovery.metadata, "distributions", lambda: [distribution])
    info = discovery.get_installed_plugin("ResearchPlugin")
    assert info.error is None
    assert info.plugins == artifact.plugins == ["ResearchPlugin"]
    assert info.content_sha256 == artifact.content_sha256
    assert info.sha256 == artifact.sha256
    assert info.tasks == artifact.tasks
    assert main(["plugin", "inspect", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["plugins"] == info.plugins
    assert result["wheel"] == str(path)
    assert result["content_sha256"] == info.content_sha256


def test_content_identity_ignores_archive_compression_and_installed_bytecode(tmp_path, monkeypatch):
    path = make_wheel(tmp_path)
    first = wheel.inspect_wheel(path)
    distribution = installed_distribution(path, tmp_path / "installed")
    package = tmp_path / "installed/example_plugin"
    (package / "__pycache__").mkdir()
    (package / "__pycache__/cached.pyc").write_bytes(b"compiled")
    monkeypatch.setattr(discovery.metadata, "distributions", lambda: [distribution])
    assert discovery.get_installed_plugin("example_plugin").content_sha256 == first.content_sha256
    second = wheel.inspect_wheel(make_wheel(tmp_path, compression=ZIP_DEFLATED))
    assert second.sha256 != first.sha256
    assert second.content_sha256 == first.content_sha256
    (package / "__init__.py").write_text("changed = True")
    assert discovery.get_installed_plugin("example-plugin").content_sha256 != first.content_sha256


def test_conflicting_archive_members_are_not_hidden_by_duplicate_filenames(tmp_path):
    path = make_wheel(tmp_path)
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(path, "a") as archive:
            archive.writestr("example_plugin/__init__.py", "changed = True")
    with pytest.raises(ValueError, match="Conflicting plugin wheel file"):
        wheel.inspect_wheel(path)


@pytest.mark.parametrize("text", ["[", "[]", '{"archive_info": null}', '{"archive_info": {"hashes": []}}'])
def test_malformed_provenance_does_not_hide_an_installed_plugin(tmp_path, monkeypatch, text):
    distribution = installed_distribution(make_wheel(tmp_path), tmp_path / "installed", provenance=text)
    monkeypatch.setattr(discovery.metadata, "distributions", lambda: [distribution])
    info = discovery.get_installed_plugin("example-plugin")
    assert info.error is None
    assert info.sha256 is None


@pytest.mark.parametrize("manifest", ["[]", "tasks: [", "components: {}", "tasks: {research: 1}"])
def test_invalid_manifests_fail_wheel_inspection_and_remain_visible_in_discovery(tmp_path, monkeypatch, manifest):
    path = make_wheel(tmp_path, packages={"example": ("example_plugin", manifest)})
    with pytest.raises(ValueError, match="manifest"):
        wheel.inspect_wheel(path)
    distribution = installed_distribution(path, tmp_path / "installed")
    monkeypatch.setattr(discovery.metadata, "distributions", lambda: [distribution])
    info = discovery.get_installed_plugin("example")
    assert info.error
    assert not info.tasks
    assert discovery.discover_task_registrations() == []


def test_manifests_reject_duplicate_tasks_and_invalid_packages_before_reading():
    packages = {"one": "first", "two": "second"}
    with pytest.raises(ValueError, match="Duplicate Task"):
        PluginManifest.from_packages(packages, lambda package: "tasks: {same: package:Task}")
    for package in ("package:Class", "../package", "", "package..nested"):
        with pytest.raises(ValueError, match="must target a package"):
            PluginManifest.from_packages({"one": package}, lambda value: pytest.fail("Read an invalid package"))


def test_discovery_keeps_the_first_distribution_on_the_import_path(tmp_path, monkeypatch):
    path = make_wheel(tmp_path)
    first = installed_distribution(path, tmp_path / "first")
    second = installed_distribution(path, tmp_path / "second")
    (tmp_path / "second/example_plugin/plugin.yaml").write_text("tasks: {shadowed: missing:Task}")
    monkeypatch.setattr(discovery.metadata, "distributions", lambda: [first, second])
    plugins = discovery.list_installed_plugins()
    assert len(plugins) == 1
    assert set(plugins[0].tasks) == {"research"}
    assert discovery.discover_task_registrations() == [
        ("research", "axonx.task.builtins.demo:DemoTask", "example-plugin")
    ]


def test_task_registration_discovery_does_not_import_plugin_code_or_compute_fingerprints(tmp_path, monkeypatch):
    distribution = installed_distribution(make_wheel(tmp_path), tmp_path / "installed")
    monkeypatch.setattr(discovery.metadata, "distributions", lambda: [distribution])
    monkeypatch.setattr(
        discovery, "content_sha256_from_directories", lambda **kwargs: pytest.fail("Computed a content fingerprint")
    )
    monkeypatch.setattr(discovery, "_wheel_sha256", lambda value: pytest.fail("Read wheel provenance"))
    assert discovery.discover_task_registrations() == [
        ("research", "axonx.task.builtins.demo:DemoTask", "example-plugin")
    ]


def test_source_cache_ignores_generated_files_but_tracks_nested_source_and_rejects_symlinks(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'")
    first = fingerprint.source_sha256(tmp_path)
    for ignored in ("build", "dist", ".git", "example.egg-info", "__pycache__"):
        directory = tmp_path / ignored
        directory.mkdir()
        (directory / "generated").write_text("ignored")
    assert fingerprint.source_sha256(tmp_path) == first
    nested = tmp_path / "package/build"
    nested.mkdir(parents=True)
    (nested / "source.py").write_text("included = True")
    assert fingerprint.source_sha256(tmp_path) != first
    (tmp_path / "linked.py").symlink_to(nested / "source.py")
    with pytest.raises(ValueError, match="symlinks"):
        fingerprint.source_sha256(tmp_path)


def test_preparation_reuses_source_cache_and_explicit_output_rebuilds(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname = 'example'")
    builds = []

    def build(command, **kwargs):
        output = Path(command[command.index("--wheel-dir") + 1])
        builds.append(output)
        make_wheel(output)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(wheel.subprocess, "run", build)
    first = installer.prepare_artifact(source, cache_dir=tmp_path / "cache")
    assert installer.prepare_artifact(source, cache_dir=tmp_path / "cache").sha256 == first.sha256
    assert len(builds) == 1
    assert not list(first.wheel.parent.glob(".build-*"))
    installer.prepare_artifact(source, cache_dir=tmp_path / "cache", output=tmp_path / "output")
    installer.prepare_artifact(source, cache_dir=tmp_path / "cache", output=tmp_path / "output")
    assert len(builds) == 3
    with pytest.raises(ValueError, match="existing wheel"):
        installer.prepare_artifact(first.wheel, cache_dir=tmp_path / "cache", output=tmp_path / "output")


def test_install_preserves_the_host_and_checks_provenance_and_content(tmp_path, monkeypatch):
    artifact = wheel.inspect_wheel(make_wheel(tmp_path))
    info = PluginInfo(**artifact.model_dump(exclude={"wheel"}))
    commands = []
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command) or SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    monkeypatch.setattr(installer, "get_installed_plugin", lambda name: info)
    assert installer.install_plugin(artifact) == info
    assert commands[0] == [sys.executable, "-m", "pip", "install", "packaging>=20"]
    assert commands[1][-2:] == ["--no-deps", str(artifact.wheel)]
    for field, message in (
        ("sha256", "provenance mismatch"),
        ("content_sha256", "content mismatch"),
        ("error", "invalid"),
    ):
        broken = info.model_copy(update={field: "changed"})
        monkeypatch.setattr(installer, "get_installed_plugin", lambda name, value=broken: value)
        with pytest.raises(RuntimeError, match=message):
            installer.install_plugin(artifact)


def test_editable_install_discovers_in_a_fresh_interpreter(tmp_path, monkeypatch):
    artifact = wheel.inspect_wheel(make_wheel(tmp_path))
    info = PluginInfo(distribution=artifact.distribution, version=artifact.version, tasks=artifact.tasks)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stderr="", stdout=info.model_dump_json() if command[1] == "-c" else "")

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer, "get_installed_plugin", lambda name: pytest.fail("Used stale interpreter hooks"))
    assert installer.install_plugin(artifact, editable_source=tmp_path) == info
    assert commands[1][-2:] == ["--editable", str(tmp_path)]
    assert commands[2][:2] == [sys.executable, "-c"]
    assert commands[2][-1] == artifact.distribution


def test_uninstall_allows_broken_plugins_and_reports_pip_failures(monkeypatch):
    info = PluginInfo(distribution="example", version="1", error="missing manifest")
    monkeypatch.setattr(installer, "get_installed_plugin", lambda name: info)
    commands = []
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command) or SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    assert installer.uninstall_plugin("example") == {"distribution": "example"}
    assert commands == [[sys.executable, "-m", "pip", "uninstall", "--yes", "example"]]
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(returncode=1, stderr="pip failed", stdout=""),
    )
    with pytest.raises(RuntimeError, match="uninstall failed: pip failed"):
        installer.uninstall_plugin("example")


@pytest.mark.parametrize("contents", [b"not a zip", b""])
def test_invalid_wheels_return_a_cli_error(tmp_path, capsys, contents):
    path = tmp_path / "broken.whl"
    path.write_bytes(contents)
    assert main(["plugin", "inspect", str(path)]) == 2
    assert "Not a readable plugin wheel" in capsys.readouterr().err
