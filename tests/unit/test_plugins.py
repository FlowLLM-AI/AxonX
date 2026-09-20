"""Plugin lifecycle tests for the environment-backed implementation."""

from pathlib import Path

import pytest

from axonx import Application
from axonx.components.client import ClientOptions
from axonx.components.job import JobResponse, ResultEvent
from axonx.config import ConfigResolver
from axonx.components.client.remote import stream_remote_job
from axonx.plugin_kit import PluginArtifact, PluginInfo, index_contributions
from axonx.plugin_kit.cli import plugin_cli
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
        sha256=sha256,
        components={},
        jobs={},
    )


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


def test_remote_verification_compares_active_wheel_digest(monkeypatch):
    monkeypatch.setattr(
        "axonx.plugin_kit.verification.installed_plugin_for_task",
        lambda _task: ("demo", "local"),
    )

    with pytest.raises(ValueError, match="wheel SHA-256 differs"):
        verify_remote_plugin(
            "demo_task",
            [
                {
                    "distribution": "demo",
                    "tasks": {"demo_task": "demo:Task"},
                    "sha256": "remote",
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
