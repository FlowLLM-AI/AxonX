"""Plugin lifecycle tests for the environment-backed implementation."""

from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from axonx.app.components.client.remote import stream_remote_job
from axonx.app.components.job import ResultEvent
from axonx.cli.plugin import plugin_cli
from axonx.plugin import PluginArtifact, PluginInfo, index_contributions
from axonx.plugin.discovery import _package_path
from axonx.plugin.identity import content_sha256_from_directories, content_sha256_from_wheel
from axonx.plugin.wheel import source_sha256


def _artifact(path: Path, sha256: str) -> PluginArtifact:
    return PluginArtifact(
        distribution="demo-plugin",
        version="1.0",
        plugin_names=("demo",),
        tasks={},
        requirements=(),
        wheel=path,
        content_sha256="content",
        sha256=sha256,
    )


def test_content_sha_is_independent_of_directory_or_wheel_packaging(tmp_path):
    source = tmp_path / "source" / "demo_plugin"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "plugin.yaml").write_text("tasks: {}\n", encoding="utf-8")
    cache = source / "__pycache__"
    cache.mkdir()
    (cache / "ignored.pyc").write_bytes(b"host-specific")

    wheel = tmp_path / "demo.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("demo_plugin/plugin.yaml", "tasks: {}\n")
        archive.writestr("demo_plugin/__init__.py", "VALUE = 1\n")
        archive.writestr("demo_plugin/__pycache__/ignored.pyc", b"other-host")
        archive.writestr("demo_plugin-1.0.dist-info/RECORD", "volatile")

    arguments = {
        "distribution": "demo-plugin",
        "version": "1.0",
        "requirements": ["dependency>=1"],
        "plugins": {"demo": "demo_plugin"},
    }
    directory_hash = content_sha256_from_directories(**arguments, package_paths={"demo_plugin": source})
    with ZipFile(wheel) as archive:
        wheel_hash = content_sha256_from_wheel(archive, **arguments)

    assert directory_hash == wheel_hash


def test_content_sha_changes_when_plugin_content_changes(tmp_path):
    package = tmp_path / "demo_plugin"
    package.mkdir()
    source = package / "__init__.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    arguments = {
        "distribution": "demo-plugin",
        "version": "1.0",
        "requirements": [],
        "plugins": {"demo": "demo_plugin"},
        "package_paths": {"demo_plugin": package},
    }
    before = content_sha256_from_directories(**arguments)

    source.write_text("VALUE = 2\n", encoding="utf-8")

    assert content_sha256_from_directories(**arguments) != before


@pytest.mark.parametrize(
    "generated",
    [
        "node_modules",
        "web/node_modules",
        ".axonx",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        ".nox",
        ".git",
        ".venv",
        "__pycache__",
        "demo.egg-info",
        "package/demo.egg-info",
    ],
)
def test_source_hash_ignores_generated_directories_without_traversing(tmp_path, monkeypatch, generated):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    source = tmp_path / "source.py"
    source.write_text("VALUE = 1\n")
    before = source_sha256(tmp_path)
    output = tmp_path / generated
    output.mkdir(parents=True)
    (output / "link").symlink_to(source)
    iterdir = Path.iterdir

    def guarded_iterdir(path):
        assert path != output, "Generated directories must not be traversed"
        return iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    assert source_sha256(tmp_path) == before
    source.write_text("VALUE = 2\n")
    assert source_sha256(tmp_path) != before


@pytest.mark.parametrize("directory", ["build", "dist"])
def test_source_hash_keeps_nested_build_sources_and_rejects_source_symlinks(tmp_path, directory):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    nested = tmp_path / "package" / directory
    nested.mkdir(parents=True)
    source = nested / "source.py"
    source.write_text("VALUE = 1\n")
    before = source_sha256(tmp_path)
    output = tmp_path / directory
    output.mkdir()
    (output / "link").symlink_to(source)
    assert source_sha256(tmp_path) == before
    source.write_text("VALUE = 2\n")
    assert source_sha256(tmp_path) != before
    (nested / "link").symlink_to(source)
    with pytest.raises(ValueError, match="does not allow symlinks"):
        source_sha256(tmp_path)


@pytest.mark.parametrize("relative", [".DS_Store", "package/.DS_Store"])
def test_source_hash_ignores_generated_files(tmp_path, relative):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    before = source_sha256(tmp_path)
    generated = tmp_path / relative
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"metadata")
    assert source_sha256(tmp_path) == before
    generated.write_bytes(b"updated metadata")
    assert source_sha256(tmp_path) == before


def test_editable_plugin_package_uses_import_location(monkeypatch, tmp_path):
    package = tmp_path / "src" / "demo_plugin"
    package.mkdir(parents=True)
    distribution = SimpleNamespace(locate_file=lambda relative: tmp_path / "site-packages" / relative)
    specification = SimpleNamespace(submodule_search_locations=[str(package)])
    monkeypatch.setattr("axonx.plugin.discovery.util.find_spec", lambda _package: specification)

    assert _package_path(distribution, "demo_plugin") == package.resolve()


def test_contribution_index_rejects_duplicate_public_names():
    one = PluginInfo(distribution="one", version="1", tasks={"shared": "one:Task"})
    two = PluginInfo(distribution="two", version="1", tasks={"shared": "two:Task"})

    with pytest.raises(ValueError, match="provided by plugins 'one' and 'two'"):
        index_contributions([one, two])


def test_plugin_cli_lists_local_environment_by_default(monkeypatch, capsys):
    plugin = PluginInfo(distribution="local-demo", version="1")
    monkeypatch.setattr("axonx.cli.plugin.list_installed_plugins", lambda: [plugin])
    assert plugin_cli(["list"]) == 0
    assert '"distribution": "local-demo"' in capsys.readouterr().out


def test_plugin_cli_installs_locally_by_default(monkeypatch, capsys):
    plugin = PluginInfo(distribution="local-demo", version="1")
    artifact = object()
    monkeypatch.setattr("axonx.cli.plugin.prepare_artifact", lambda *_args, **_kwargs: artifact)
    monkeypatch.setattr(
        "axonx.cli.plugin.install_plugin",
        lambda received, **_options: plugin if received is artifact else None,
    )
    assert plugin_cli(["install", "source"]) == 0
    assert '"distribution": "local-demo"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_streamed_submit_calls_selected_service(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def stream_job(self, name, arguments):
            assert name == "submit"
            assert arguments == {"task": "demo_task"}
            yield ResultEvent(answer="ok")

    monkeypatch.setattr(
        "axonx.app.components.client.remote.HttpClient",
        lambda **options: Client(),
    )

    events = [event async for event in stream_remote_job("submit", {"task": "demo_task"}, target="10.0.0.2:1024")]

    assert events[0].answer == "ok"


@pytest.mark.parametrize("flag", ["-e", "--editable"])
def test_plugin_cli_installs_editable_locally(monkeypatch, tmp_path, flag):
    plugin = PluginInfo(distribution="editable-demo", version="1")
    artifact = object()
    monkeypatch.setattr("axonx.cli.plugin.prepare_artifact", lambda *_args, **_kwargs: artifact)

    def install(received, *, editable_source):
        assert received is artifact
        assert editable_source == tmp_path.resolve()
        return plugin

    monkeypatch.setattr("axonx.cli.plugin.install_plugin", install)
    assert plugin_cli(["install", flag, str(tmp_path)]) == 0


def test_editable_rejects_output(monkeypatch, capsys):
    def unexpected(*_args):
        pytest.fail("Invalid editable options must fail before building or installing")

    monkeypatch.setattr("axonx.cli.plugin.install_plugin", unexpected)
    assert plugin_cli(["install", "-e", "plugins/demo", "--output", "dist"]) == 1
    assert "--output" in capsys.readouterr().err


@pytest.mark.parametrize("editable", [False, True])
def test_plugin_install_preserves_axonx_and_installs_dependencies(monkeypatch, tmp_path, editable):
    from dataclasses import replace

    from axonx.plugin.wheel import install_artifact

    artifact = replace(
        _artifact(tmp_path / "demo.whl", "digest"),
        requirements=("AxonX>=0.1", "example-dependency>=1"),
    )
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("axonx.plugin.wheel.subprocess.run", run)
    source = tmp_path / "source" if editable else None
    install_artifact(artifact, editable_source=source)
    assert commands[0][3:] == ["install", "example-dependency>=1"]
    assert "--no-deps" in commands[1]
    if editable:
        assert commands[1][-2:] == ["--editable", str(source)]
    else:
        assert commands[1][-1] == str(artifact.wheel)
        assert "--editable" not in commands[1]


@pytest.mark.parametrize("failure", [None, "discovery", "invalid"])
def test_editable_install_checks_plugin_in_new_interpreter(monkeypatch, tmp_path, failure):
    from axonx.plugin.installer import install_plugin

    artifact = _artifact(tmp_path / "demo.whl", "digest")
    plugin = PluginInfo(
        distribution=artifact.distribution,
        version="1",
        error="invalid" if failure == "invalid" else None,
    )
    monkeypatch.setattr("axonx.plugin.installer.install_artifact", lambda *_args, **_kwargs: None)

    def run(command, **_kwargs):
        assert command[-1] == artifact.distribution
        assert "get_installed_plugin" in command[-2]
        return SimpleNamespace(
            returncode=int(failure == "discovery"),
            stdout=plugin.model_dump_json(),
            stderr="failed",
        )

    monkeypatch.setattr("axonx.plugin.installer.subprocess.run", run)
    if failure:
        with pytest.raises(
            RuntimeError,
            match="discovery failed" if failure == "discovery" else "invalid",
        ):
            install_plugin(artifact, editable_source=tmp_path)
    else:
        assert install_plugin(artifact, editable_source=tmp_path) == plugin
