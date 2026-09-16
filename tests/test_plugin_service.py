"""Plugin service failure and contribution consistency tests."""

# pylint: disable=missing-function-docstring

from pathlib import Path

import pytest

from axonx.components.plugin.local.contributions import index_records
from axonx.components.plugin.local.repository import PluginRepository
from axonx.components.plugin.local.service import PluginService
from axonx.plugin.cli import plugin_job_argv
from axonx.plugin import PluginArtifact


def artifact(path: Path, *, tasks: dict[str, str] | None = None) -> PluginArtifact:
    return PluginArtifact(
        distribution="demo",
        version="0.1",
        plugin_names=("demo",),
        tasks=tasks or {},
        requirements=(),
        wheel=path,
        sha256="digest",
        components={},
        jobs={},
    )


def test_uploaded_wheel_rejects_digest_without_install_or_state(monkeypatch, tmp_path):
    repository = PluginRepository(tmp_path)
    installed = []
    service = PluginService(repository, installed.append)
    monkeypatch.setattr("axonx.components.plugin.local.service.inspect_wheel", artifact)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        service.install_uploaded_wheel(b"wheel", "demo.whl", "wrong")

    assert not installed
    assert repository.records == {}
    assert not repository.path.exists()


def test_install_failure_keeps_previous_state(monkeypatch, tmp_path):
    repository = PluginRepository(tmp_path)
    repository.record("existing", artifact(tmp_path / "old.whl"))
    before = repository.path.read_bytes()

    def fail(_artifact):
        raise RuntimeError("pip failed")

    service = PluginService(repository, fail)
    monkeypatch.setattr("axonx.components.plugin.local.service.inspect_wheel", artifact)

    with pytest.raises(RuntimeError, match="pip failed"):
        service.install_uploaded_wheel(b"wheel", "demo.whl", "digest")

    assert repository.path.read_bytes() == before
    assert list(repository.records) == ["existing"]


def test_repeated_upload_skips_installer(monkeypatch, tmp_path):
    repository = PluginRepository(tmp_path)
    installed = []
    service = PluginService(repository, installed.append)
    monkeypatch.setattr("axonx.components.plugin.local.service.inspect_wheel", artifact)

    service.install_uploaded_wheel(b"wheel", "demo.whl", "digest")
    before = repository.path.read_bytes()
    service.install_uploaded_wheel(b"wheel", "demo.whl", "digest")

    assert len(installed) == 1
    assert repository.path.read_bytes() == before


def test_conflicting_task_contributions_rejected_before_install(monkeypatch, tmp_path):
    repository = PluginRepository(tmp_path)
    repository.records = {"other": {"tasks": {"shared": "other:Task"}}}
    installed = []
    service = PluginService(repository, installed.append)
    monkeypatch.setattr(
        "axonx.components.plugin.local.service.inspect_wheel",
        lambda path: artifact(path, tasks={"shared": "demo:Task"}),
    )

    with pytest.raises(ValueError, match="provided by plugins"):
        service.install_uploaded_wheel(b"wheel", "demo.whl", "digest")

    assert not installed
    assert "remote:demo" not in repository.records


def test_conflicting_job_and_component_contributions():
    with pytest.raises(ValueError, match="Job 'shared'"):
        index_records({"one": {"jobs": {"shared": {}}}, "two": {"jobs": {"shared": {}}}})
    with pytest.raises(ValueError, match="Component backend step:demo"):
        index_records(
            {
                "one": {"components": {"step": {"demo": "one:Step"}}},
                "two": {"components": {"step": {"demo": "two:Step"}}},
            },
        )


def test_plugin_queries_map_to_local_or_remote_jobs():
    assert plugin_job_argv(["plugin", "list"]) == ["list_plugins"]
    assert plugin_job_argv(["plugin", "status", "--plugin", "demo"]) == ["status_plugins", "--plugin", "demo"]
    assert plugin_job_argv(["plugin", "inspect", "--plugin", "demo", "--host-ip", "10.0.0.2"]) == [
        "--host-ip",
        "10.0.0.2",
        "inspect_plugins",
        "--plugin",
        "demo",
    ]
    assert plugin_job_argv(["--host-port", "1025", "plugin", "list"]) == [
        "--host-port",
        "1025",
        "list_plugins",
    ]
    assert plugin_job_argv(["plugin", "build", "plugins/demo"]) is None
    assert plugin_job_argv(["plugin", "install", "plugins/demo"]) is None
    assert plugin_job_argv(["plugin", "deploy", "plugins/demo"]) is None


def test_plugin_queries_reuse_job_client(monkeypatch):
    from axonx import cli

    calls = []
    monkeypatch.setattr(
        cli,
        "_run_remote_job",
        lambda command, options: calls.append((command, options)) or 0,
    )

    assert cli.main(["plugin", "status", "--plugin", "demo", "--host-ip", "127.0.0.1", "--host-port", "1025"]) == 0
    command, options = calls[0]
    assert command.action == "status_plugins"
    assert command.arguments["plugin"] == "demo"
    assert options.host_port == 1025


def test_status_and_inspect_managed_plugin(monkeypatch, tmp_path):
    wheel = tmp_path / "demo.whl"
    wheel.write_bytes(b"wheel")
    repository = PluginRepository(tmp_path)
    repository.record("remote:demo", artifact(wheel))
    service = PluginService(repository, lambda _artifact: None)
    monkeypatch.setattr("axonx.components.plugin.local.service.inspect_wheel", artifact)

    assert service.status("demo")["version"] == "0.1"
    assert service.inspect("demo")["requirements"] == ()
    with pytest.raises(ValueError, match="Unknown plugin"):
        service.status("missing")


def test_inspect_rejects_changed_managed_wheel(monkeypatch, tmp_path):
    wheel = tmp_path / "demo.whl"
    wheel.write_bytes(b"changed")
    repository = PluginRepository(tmp_path)
    repository.record("remote:demo", artifact(wheel))
    service = PluginService(repository, lambda _artifact: None)

    def inspect(path):
        return artifact(path).model_copy(update={"sha256": "changed"})

    monkeypatch.setattr("axonx.components.plugin.local.service.inspect_wheel", inspect)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        service.inspect("demo")


@pytest.mark.asyncio
async def test_plugin_query_jobs_use_service_state(monkeypatch, tmp_path):
    from axonx import Application
    from axonx.config import resolve_app_config

    wheel = tmp_path / "demo.whl"
    wheel.write_bytes(b"wheel")
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    PluginRepository(plugin_dir).record("remote:demo", artifact(wheel))
    monkeypatch.setattr("axonx.components.plugin.local.service.inspect_wheel", artifact)
    configured = resolve_app_config(log_config=False)["jobs"]
    jobs = {name: configured[name] for name in ("list_plugins", "status_plugins", "inspect_plugins")}
    app = Application(
        workspace_dir=str(tmp_path),
        components={"plugin": {"default": {"backend": "local"}}},
        jobs=jobs,
    )

    async with app:
        listed = await app.run_job("list_plugins")
        status = await app.run_job("status_plugins", plugin="demo")
        inspected = await app.run_job("inspect_plugins", plugin="demo")

    assert listed.answer[0]["distribution"] == "demo"
    assert status.answer["version"] == "0.1"
    assert inspected.answer["requirements"] == ()
