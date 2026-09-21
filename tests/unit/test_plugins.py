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
from axonx.plugin_kit.verification import verify_remote_plugin
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
    directory_hash = content_sha256_from_directories(
        **arguments, package_paths={"demo_plugin": source}
    )
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
    distribution = SimpleNamespace(
        locate_file=lambda relative: tmp_path / "site-packages" / relative
    )
    specification = SimpleNamespace(submodule_search_locations=[str(package)])
    monkeypatch.setattr(
        "axonx.plugin_kit.discovery.util.find_spec", lambda _package: specification
    )

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
        lambda path: _artifact(
            Path(path), expected if Path(path) == staged else "b" * 64
        ),
    )

    with pytest.raises(ValueError, match="Stored plugin wheel SHA-256 mismatch"):
        install_staged_plugin(staged, expected, tmp_path / "artifacts")


@pytest.mark.asyncio
async def test_install_job_discards_staged_wheel_when_installation_fails(
    monkeypatch, tmp_path
):
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
        plugins={"allow_remote_management": True},
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


def test_plugin_cli_uses_local_environment_without_client_address(monkeypatch, capsys):
    plugin = PluginInfo(distribution="demo", version="1")
    monkeypatch.setattr("axonx.plugin_kit.cli.list_installed_plugins", lambda: [plugin])

    assert plugin_cli(["list"], ClientOptions()) == 0
    assert '"distribution": "demo"' in capsys.readouterr().out


def test_plugin_cli_uses_jobs_when_client_address_is_supplied(monkeypatch, capsys):
    plugin = PluginInfo(distribution="remote-demo", version="1")

    async def remote(args, options):
        assert args.command == "list"
        assert options.host_ip == "127.0.0.1"
        return [plugin]

    monkeypatch.setattr("axonx.plugin_kit.cli._run_remote", remote)

    options = ClientOptions(host_ip="127.0.0.1", host_port=1024)
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

    options = ClientOptions(host_ip="127.0.0.1", host_port=1024)
    assert plugin_cli(["install", str(wheel)], options) == 1
    assert discarded == ["copies/demo.whl"]


def test_remote_verification_compares_active_content_digest(monkeypatch):
    monkeypatch.setattr(
        "axonx.plugin_kit.verification.installed_plugin_for_task",
        lambda _task: ("demo", "local-content", None),
    )

    with pytest.raises(ValueError, match="content SHA-256 differs"):
        verify_remote_plugin(
            "demo_task",
            [
                {
                    "distribution": "demo",
                    "tasks": {"demo_task": "demo:Task"},
                    "content_sha256": "remote-content",
                    "sha256": None,
                }
            ],
        )


def test_remote_verification_accepts_matching_content_for_source_installs(monkeypatch):
    monkeypatch.setattr(
        "axonx.plugin_kit.verification.installed_plugin_for_task",
        lambda _task: ("demo", "same-content", None),
    )

    verify_remote_plugin(
        "demo_task",
        [
            {
                "distribution": "demo",
                "tasks": {"demo_task": "demo:Task"},
                "content_sha256": "same-content",
                "sha256": None,
            }
        ],
    )


def test_remote_verification_falls_back_to_wheel_digest(monkeypatch):
    monkeypatch.setattr(
        "axonx.plugin_kit.verification.installed_plugin_for_task",
        lambda _task: ("demo", "local-content", "same-wheel"),
    )

    verify_remote_plugin(
        "demo_task",
        [
            {
                "distribution": "demo",
                "tasks": {"demo_task": "demo:Task"},
                "sha256": "same-wheel",
            }
        ],
    )


def test_remote_verification_rejects_different_fallback_wheels(monkeypatch):
    monkeypatch.setattr(
        "axonx.plugin_kit.verification.installed_plugin_for_task",
        lambda _task: ("demo", None, "local-wheel"),
    )

    with pytest.raises(ValueError, match="wheel SHA-256 differs"):
        verify_remote_plugin(
            "demo_task",
            [
                {
                    "distribution": "demo",
                    "tasks": {"demo_task": "demo:Task"},
                    "sha256": "remote-wheel",
                }
            ],
        )


@pytest.mark.asyncio
async def test_streamed_submit_verifies_plugins_before_remote_job(monkeypatch):
    verified: list[str] = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def stream_job(self, _name, _arguments, *, remote_ip=None):
            yield ResultEvent(answer={"remote_ip": remote_ip})

    async def verify(_client, job_name, arguments):
        assert job_name == "submit"
        verified.append(arguments["task"])

    monkeypatch.setattr(
        "axonx.components.client.remote.HttpClient",
        lambda **_options: Client(),
    )

    events = [
        event
        async for event in stream_remote_job(
            "submit",
            {"task": "demo_task"},
            target_ip="10.0.0.2",
            preflight=verify,
        )
    ]

    assert verified == ["demo_task"]
    assert events[0].answer == {"remote_ip": "10.0.0.2"}
