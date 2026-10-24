"""Exercise CLI forwarding through real HTTP and isolated subprocesses."""

import asyncio
import importlib
import json
import os
import socket
import sys
import venv
from pathlib import Path

import pytest
import uvicorn
from test_plugin_hot_update import wheel

from axonx.components.client import HttpClient
from axonx.components.job import LogEvent
from axonx.config import resolve_app_config
from axonx.core import Application

cli = importlib.import_module("axonx.cli.main")


@pytest.fixture
async def remote(tmp_path):
    config = resolve_app_config(log_config=False)
    config.update(
        workspace_dir=str(tmp_path / "workspace"),
        log_dir=str(tmp_path / "logs"),
        log_to_console=False,
        log_to_file=False,
        enable_logo=False,
    )
    config["components"] = {"updater": {"default": {"backend": "local"}}}
    config["jobs"] = {name: config["jobs"][name] for name in ("cli", "version", "python", "restart_service")}
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    config["service"].update(host="127.0.0.1", port=port, token="secret", web_enabled=False)
    app = Application(**config)
    service = app.context.service
    server = uvicorn.Server(uvicorn.Config(service.build_service(app), log_level="error"))
    service.server = server
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield app, f"127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)


async def invoke(target, *argv):
    return await asyncio.to_thread(cli.main, [*argv, "--target", target, "--token", "secret"])


async def test_remote_job_preserves_json_and_stream_format(remote, capsys):
    _app, target = remote
    assert await invoke(target, "version") == 0
    assert json.loads(capsys.readouterr().out)["success"] is True
    assert await invoke(target, "version", "--stream", "true", "--stream-format", "json") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["kind"] == "result"
    assert result["success"] is True


async def test_remote_exec_uses_service_workspace_and_preserves_errors(remote, capsys):
    app, target = remote
    assert await invoke(target, "exec", "--task", "demo", "--x", "2", "--y", "3") == 0
    output = capsys.readouterr().out
    assert '"result": 5' in output
    assert list(app.workspace_path.glob("base/*/metadata.json"))
    assert await invoke(target, "exec", "--task", "missing") == 2
    assert "Unknown Task" in capsys.readouterr().err
    assert not app.context.service.cli_processes


async def test_remote_argv_preserves_multiline_unicode_and_business_timeout(remote, capsys):
    _app, target = remote
    source = 'import sys\nprint("中文 --target literal")\nprint("error text", file=sys.stderr)'
    assert await invoke(target, "python", "--code", source, "--timeout", "10") == 0
    answer = json.loads(capsys.readouterr().out)["answer"]
    assert answer["stdout"] == "中文 --target literal\n"
    assert answer["stderr"] == "error text\n"


@pytest.mark.parametrize("argv", [["start"], ["cli", "--argv", '["version"]'], ["version", "--target", "other:1024"]])
async def test_remote_cli_rejects_service_start_and_recursive_forwarding(remote, argv):
    app, target = remote
    async with HttpClient(target=target, token="secret") as client:
        response = await client.run_job("cli", {"argv": argv})
    assert not response.success
    assert not app.context.service.cli_processes


async def test_closing_cli_stream_reaps_owned_process(remote, monkeypatch):
    app, _target = remote
    create = asyncio.create_subprocess_exec

    async def spawn(*_args, **kwargs):
        return await create(sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)", **kwargs)

    monkeypatch.setattr("axonx.steps.common.cli.asyncio.create_subprocess_exec", spawn)
    events = app.stream_job("cli", {"argv": ["version"]})
    async with asyncio.timeout(10):
        event = await anext(events)
        assert isinstance(event, LogEvent) and "ready" in event.content
        (pid,) = app.context.service.cli_processes
        await events.aclose()
    assert not app.context.service.cli_processes
    assert not app.context.service.cli_callbacks
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_cancellation_during_spawn_reaps_the_created_process(remote, monkeypatch):
    app, _target = remote
    create = asyncio.create_subprocess_exec
    created, release = asyncio.Event(), asyncio.Event()
    processes = []

    async def spawn(*_args, **kwargs):
        process = await create(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        processes.append(process)
        created.set()
        await release.wait()
        return process

    monkeypatch.setattr("axonx.steps.common.cli.asyncio.create_subprocess_exec", spawn)
    task = asyncio.create_task(app.run_job("cli", {"argv": ["version"]}))
    async with asyncio.timeout(10):
        await created.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert processes[0].returncode is not None
    assert not app.context.service.cli_processes
    assert not app.context.service.cli_callbacks


async def test_json_cli_response_bounds_output_and_preserves_exit_code(remote, monkeypatch):
    app, _target = remote
    create = asyncio.create_subprocess_exec

    async def spawn(*_args, **kwargs):
        source = "import sys; print('x' * (1024 * 1024 + 1)); print('failed', file=sys.stderr); sys.exit(7)"
        return await create(sys.executable, "-u", "-c", source, **kwargs)

    monkeypatch.setattr("axonx.steps.common.cli.asyncio.create_subprocess_exec", spawn)
    response = await app.run_job("cli", {"argv": ["version"]})
    assert not response.success
    assert response.answer["exit_code"] == 7
    assert len(response.answer["stdout"]) == 1024 * 1024
    assert response.answer["stdout_truncated"] is True
    assert response.answer["stderr"] == "failed\n"


async def test_upload_then_plugin_install_uses_remote_path_without_consuming_upload(
    remote, tmp_path, monkeypatch, capsys
):
    app, target = remote
    environment = tmp_path / "venv"
    await asyncio.to_thread(venv.EnvBuilder(with_pip=True, system_site_packages=True).create, environment)
    artifact = wheel(
        tmp_path,
        "remote_cli_test",
        {"task.py": "from axonx.task.builtins.demo import DemoTask\n"},
        {"remote_cli_demo": "remote_cli_test.task:DemoTask"},
    )
    monkeypatch.setattr(sys, "executable", str(environment / "bin" / "python"))
    async with HttpClient(target=target, token="secret") as client:
        uploaded = await client.copy_file(artifact)
        assert Path(uploaded.location).is_absolute()
        assert await invoke(target, "plugin", "install", uploaded.location) == 0
        assert json.loads(capsys.readouterr().out)["distribution"] == "remote_cli_test"
        assert Path(uploaded.location).is_file()
        assert await invoke(target, "plugin", "show", "remote-cli-test") == 0
        assert "remote_cli_demo" in capsys.readouterr().out
        assert await invoke(target, "plugin", "uninstall", "remote-cli-test") == 0
        capsys.readouterr()
        await client.discard_file(uploaded.path)
        assert not Path(uploaded.location).exists()
    assert not app.context.service.cli_processes


async def test_restart_waits_for_outer_cli_response(remote, monkeypatch, capsys):
    from axonx.daemon import client as daemon

    app, target = remote
    updater = app.context.components["updater"]["default"]
    calls = []
    monkeypatch.setenv(daemon.SOCKET, "test-socket")
    monkeypatch.setattr(updater, "_plan", lambda *_: {"cwd": str(app.workspace_path)})
    monkeypatch.setattr(daemon, "request", lambda action, **_: calls.append(action) or {"update_id": "a" * 32})
    assert await invoke(target, "restart_service") == 0
    assert json.loads(capsys.readouterr().out)["success"] is True
    assert calls == ["prepare_update", "commit_update"]
    assert not app.context.service.server.should_exit
