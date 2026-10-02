"""Plugin lifecycle tests for the environment-backed implementation."""

from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from axonx import Application
from axonx.components.client import ClientOptions
from axonx.components.client.remote import stream_remote_job
from axonx.components.job import JobResponse, ResultEvent
from axonx.config import ConfigResolver
from axonx.plugin_kit import PluginArtifact, PluginInfo, index_contributions
from axonx.plugin_kit.cli import plugin_cli
from axonx.plugin_kit.discovery import _package_path
from axonx.plugin_kit.identity import (
    content_sha256_from_directories,
    content_sha256_from_wheel,
)
from axonx.plugin_kit.installer import install_staged_plugin
from axonx.workspace.models import FileCopy
from axonx.workspace.staging import StagedFiles


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
        components={},
        jobs={},
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


def test_editable_plugin_package_uses_import_location(monkeypatch, tmp_path):
    package = tmp_path / "src" / "demo_plugin"
    package.mkdir(parents=True)
    distribution = SimpleNamespace(locate_file=lambda relative: tmp_path / "site-packages" / relative)
    specification = SimpleNamespace(submodule_search_locations=[str(package)])
    monkeypatch.setattr("axonx.plugin_kit.discovery.util.find_spec", lambda _package: specification)

    assert _package_path(distribution, "demo_plugin") == package.resolve()


def test_existing_artifact_cache_is_verified_before_install(monkeypatch, tmp_path):
    staged = tmp_path / "demo.whl"
    staged.write_bytes(b"uploaded")
    expected = "a" * 64
    destination = tmp_path / "artifacts" / expected / staged.name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"tampered")

    monkeypatch.setattr(
        "axonx.plugin_kit.installer.inspect_wheel",
        lambda path: _artifact(Path(path), expected if Path(path) == staged else "b" * 64),
    )

    with pytest.raises(ValueError, match="Stored plugin wheel SHA-256 mismatch"):
        install_staged_plugin(staged, expected, tmp_path / "artifacts")


@pytest.mark.asyncio
async def test_install_job_discards_staged_wheel_when_installation_fails(monkeypatch, tmp_path):
    staged_files = StagedFiles(tmp_path)
    copied = staged_files.store(b"wheel", "demo.whl")

    def fail(*_args):
        raise RuntimeError("pip failed")

    monkeypatch.setattr("axonx.steps.plugin.install_plugin.install_staged_plugin", fail)
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        jobs={
            "install_plugin": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "sha256": {"type": "string"},
                    },
                    "required": ["path", "sha256"],
                    "additionalProperties": False,
                },
                "steps": [{"backend": "install_plugin_step"}],
            },
        },
    )

    async with app:
        response = await app.run_job(
            "install_plugin",
            {"path": copied.path, "sha256": "a" * 64},
        )

    assert response.success is False
    with pytest.raises(ValueError, match="does not exist"):
        staged_files.file(copied.path)


def test_contribution_index_rejects_duplicate_public_names():
    one = PluginInfo(distribution="one", version="1", tasks={"shared": "one:Task"})
    two = PluginInfo(distribution="two", version="1", tasks={"shared": "two:Task"})

    with pytest.raises(ValueError, match="provided by plugins 'one' and 'two'"):
        index_contributions([one, two])


def test_plugin_config_resolves_source_paths_relative_to_config(tmp_path):
    source = tmp_path / "plugin"
    source.mkdir()
    config = tmp_path / "app.yaml"
    config.write_text("plugins:\n  sources: [plugin]\n", encoding="utf-8")

    loaded = ConfigResolver(tmp_path).load(config)

    assert loaded["plugins"]["sources"] == [str(source.resolve())]


def test_plugin_cli_lists_local_environment_by_default(monkeypatch, capsys):
    plugin = PluginInfo(distribution="local-demo", version="1")
    monkeypatch.setattr("axonx.plugin_kit.cli.list_installed_plugins", lambda: [plugin])
    assert plugin_cli(["list"], ClientOptions()) == 0
    assert '"distribution": "local-demo"' in capsys.readouterr().out


def test_plugin_cli_installs_locally_by_default(monkeypatch, capsys):
    plugin = PluginInfo(distribution="local-demo", version="1")
    artifact = object()
    monkeypatch.setattr("axonx.plugin_kit.cli._artifact", lambda *_args: artifact)
    monkeypatch.setattr(
        "axonx.plugin_kit.cli.install_plugin",
        lambda received, **_options: plugin if received is artifact else None,
    )
    assert plugin_cli(["install", "source"], ClientOptions()) == 0
    assert '"distribution": "local-demo"' in capsys.readouterr().out


def test_plugin_cli_uses_jobs_when_client_address_is_supplied(monkeypatch, capsys):
    plugin = PluginInfo(distribution="remote-demo", version="1")

    async def remote(args, options):
        assert args.command == "list"
        assert options.target == "http://127.0.0.1:1024"
        return [plugin]

    monkeypatch.setattr("axonx.plugin_kit.cli._run_remote", remote)

    options = ClientOptions(target="127.0.0.1:1024")
    assert plugin_cli(["list"], options) == 0
    assert '"distribution": "remote-demo"' in capsys.readouterr().out


def test_remote_install_discards_upload_when_job_fails(monkeypatch, tmp_path):
    wheel = tmp_path / "demo.whl"
    wheel.write_bytes(b"wheel")
    artifact = _artifact(wheel, "a" * 64)
    discarded: list[str] = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def copy_file(self, _path):
            return FileCopy(path="copies/demo.whl", sha256=artifact.sha256, size=5)

        async def run_job(self, _name, _arguments):
            return JobResponse(answer="pip failed", success=False)

        async def discard_file(self, path):
            discarded.append(path)
            return path

    monkeypatch.setattr("axonx.plugin_kit.cli.HttpClient", lambda **_options: Client())
    monkeypatch.setattr("axonx.plugin_kit.cli._artifact", lambda *_args: artifact)

    options = ClientOptions(target="127.0.0.1:1024")
    assert plugin_cli(["install", str(wheel)], options) == 1
    assert discarded == ["copies/demo.whl"]


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
        "axonx.components.client.remote.HttpClient",
        lambda **options: Client(),
    )

    events = [event async for event in stream_remote_job("submit", {"task": "demo_task"}, target="10.0.0.2:1024")]

    assert events[0].answer == "ok"


@pytest.mark.parametrize("flag", ["-e", "--editable"])
def test_plugin_cli_installs_editable_locally(monkeypatch, tmp_path, flag):
    plugin = PluginInfo(distribution="editable-demo", version="1")
    artifact = object()
    monkeypatch.setattr("axonx.plugin_kit.cli._artifact", lambda *_args: artifact)

    def install(received, *, editable_source):
        assert received is artifact
        assert editable_source == tmp_path.resolve()
        return plugin

    monkeypatch.setattr("axonx.plugin_kit.cli.install_plugin", install)
    assert plugin_cli(["install", flag, str(tmp_path)]) == 0


@pytest.mark.parametrize(
    ("extra", "options", "message"),
    [
        ([], ClientOptions(target="127.0.0.1:1024"), "--target"),
        (["--output", "dist"], ClientOptions(), "--output"),
    ],
)
def test_editable_rejects_incompatible_options(extra, options, message, monkeypatch, capsys):
    def unexpected(*_args):
        pytest.fail("Invalid editable options must fail before building or installing")

    monkeypatch.setattr("axonx.plugin_kit.cli.install_plugin", unexpected)
    monkeypatch.setattr("axonx.plugin_kit.cli._run_remote", unexpected)
    assert plugin_cli(["install", "-e", "plugins/demo", *extra], options) == 1
    assert message in capsys.readouterr().err


def test_editable_rejects_wheel_before_build(monkeypatch, tmp_path, capsys):
    wheel = tmp_path / "demo.whl"
    wheel.write_bytes(b"wheel")

    def unexpected(*_args):
        pytest.fail("Editable wheels must fail before building or installing")

    monkeypatch.setattr("axonx.plugin_kit.cli._artifact", unexpected)
    assert plugin_cli(["install", "-e", str(wheel)]) == 1
    assert "project directory" in capsys.readouterr().err


@pytest.mark.parametrize("editable", [False, True])
def test_plugin_install_preserves_axonx_and_installs_dependencies(monkeypatch, tmp_path, editable):
    from dataclasses import replace
    from axonx.plugin_kit.wheel import install_artifact

    artifact = replace(
        _artifact(tmp_path / "demo.whl", "digest"),
        requirements=("AxonX>=0.1", "example-dependency>=1"),
    )
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("axonx.plugin_kit.wheel.subprocess.run", run)
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
    from axonx.plugin_kit.installer import install_plugin

    artifact = _artifact(tmp_path / "demo.whl", "digest")
    plugin = PluginInfo(
        distribution=artifact.distribution,
        version="1",
        error="invalid" if failure == "invalid" else None,
    )
    monkeypatch.setattr("axonx.plugin_kit.installer.install_artifact", lambda *_args, **_kwargs: None)

    def run(command, **_kwargs):
        assert command[-1] == artifact.distribution
        assert "get_installed_plugin" in command[-2]
        return SimpleNamespace(returncode=int(failure == "discovery"), stdout=plugin.model_dump_json(), stderr="failed")

    monkeypatch.setattr("axonx.plugin_kit.installer.subprocess.run", run)
    if failure:
        with pytest.raises(RuntimeError, match="discovery failed" if failure == "discovery" else "invalid"):
            install_plugin(artifact, editable_source=tmp_path)
    else:
        assert install_plugin(artifact, editable_source=tmp_path) == plugin
