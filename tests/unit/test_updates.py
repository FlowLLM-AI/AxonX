"""Daemon admission, response ordering and in-place update command ownership."""

import json
import os
import subprocess
import sys
import time

import httpx
import pytest

from axonx.components.updater import worker
from axonx.components.updater.manager import RESPONSE_CALLBACKS
from axonx.config import resolve_app_config
from axonx.core import Application
from axonx.components.service.http.app import _UpdateResponseMiddleware
from axonx.daemon import client as daemon


def application(tmp_path, token="secret"):
    config = resolve_app_config(log_config=False)
    config.update(
        workspace_dir=str(tmp_path / "runtime"), log_dir=str(tmp_path / "logs"), log_to_console=False, log_to_file=False
    )
    config["components"] = {"updater": {"default": {"backend": "local"}}}
    config["jobs"] = {
        name: value
        for name, value in config["jobs"].items()
        if name in {"update_from_git", "update_from_pip", "restart_service", "get_update_status", "version"}
    }
    config["service"].update(token=token, web_enabled=False)
    app = Application(**config)
    return app, app.context.components["updater"]["default"]


@pytest.mark.parametrize("failure", ["send", "cancelled", "incomplete"])
async def test_incomplete_response_does_not_commit_update(failure):
    import asyncio
    from types import SimpleNamespace

    calls = []

    async def app(_scope, _receive, send):
        RESPONSE_CALLBACKS.get().append(lambda: calls.append("committed"))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        if failure == "cancelled":
            raise asyncio.CancelledError
        await send({"type": "http.response.body", "body": b"accepted", "more_body": failure == "incomplete"})

    async def send(message):
        if failure == "send" and message["type"] == "http.response.body":
            raise ConnectionError("Client disconnected")

    middleware = _UpdateResponseMiddleware(app, SimpleNamespace(cli_callbacks={}))
    scope = {"type": "http", "headers": []}
    if failure == "incomplete":
        await middleware(scope, None, send)
    else:
        with pytest.raises(ConnectionError if failure == "send" else asyncio.CancelledError):
            await middleware(scope, None, send)
    assert not calls
    assert RESPONSE_CALLBACKS.get() is None


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("job", ["update_from_pip", "restart_service"])
async def test_response_precedes_daemon_commit_and_blocks_mutations(tmp_path, monkeypatch, stream, job):
    app, updater = application(tmp_path)
    monkeypatch.setattr(updater, "_plan", lambda *_: {"cwd": str(tmp_path)})
    monkeypatch.setenv(daemon.SOCKET, "test-socket")
    calls, sent = [], []

    def request(action, **values):
        calls.append(action)
        if action == "commit_update":
            assert sent[-1]["type"] == "http.response.body"
            assert not sent[-1].get("more_body", False)
        return {"update_id": "a" * 32, "phase": "accepted"}

    monkeypatch.setattr(daemon, "request", request)
    server = app.context.service.build_service(app)
    transport = httpx.ASGITransport(app=server)
    original = transport.app

    async def wrapped(scope, receive, output):
        async def observed(message):
            if message["type"] == "http.response.body":
                assert calls == ["prepare_update"]
                sent.append(message)
            await output(message)

        await original(scope, receive, observed)

    transport.app = wrapped
    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": "Bearer secret"}
        ) as client:
            response = await client.post("/jobs/" + job + ("/events" if stream else ""), json={"arguments": {}})
            assert response.status_code == 200
            assert calls == ["prepare_update", "commit_update"]
            transport.app = original
            assert (await client.post("/jobs/update_from_git", json={"arguments": {}})).status_code == 422


async def test_unauthenticated_service_hides_updates(tmp_path):
    app, _ = application(tmp_path, token=None)
    server = app.context.service.build_service(app)
    async with app:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
            catalog = (await client.get("/jobs")).json()["answer"]["items"]
            assert not any(item["name"].startswith("update_") for item in catalog)
            assert (await client.post("/jobs/restart_service", json={"arguments": {}})).status_code == 404


async def test_preflight_failure_releases_admission(tmp_path, monkeypatch):
    app, updater = application(tmp_path)
    monkeypatch.setenv(daemon.SOCKET, "test-socket")
    monkeypatch.setattr(updater, "_plan", lambda *_: (_ for _ in ()).throw(ValueError("bad installation")))
    token = RESPONSE_CALLBACKS.set([])
    try:
        with pytest.raises(ValueError, match="bad installation"):
            await updater.request("git")
        assert not app.context.metadata.get("maintenance")
    finally:
        RESPONSE_CALLBACKS.reset(token)


def test_status_bounds_logs_and_requires_current_scope(tmp_path):
    _, updater = application(tmp_path)
    folder = updater.directory / ("a" * 32)
    folder.mkdir(parents=True)
    worker.save(folder / "record.json", {"phase": "failed"})
    (folder / "update.log").write_bytes(b"x" * 100000)
    assert len(updater.status()["log"]) == 65536
    assert updater.status(folder.name)["record"]["phase"] == "failed"
    with pytest.raises(ValueError, match="Invalid update_id"):
        updater.status("../record.json")


def make_record(tmp_path, mode="pip"):
    path = tmp_path / "record.json"
    worker.save(path, {"mode": mode, "phase": "accepted", "error": None})
    (tmp_path / "plan.json").write_text(
        json.dumps({"cwd": str(tmp_path), "repository": str(tmp_path), "verification": "pass"})
    )
    return path


@pytest.mark.parametrize("fail", [False, True])
def test_updater_installs_in_place_without_exec_or_restart(tmp_path, monkeypatch, fail):
    path = make_record(tmp_path)
    calls = []

    def run(argv, *_):
        calls.append(argv)
        if fail:
            raise subprocess.CalledProcessError(1, argv)
        return ""

    monkeypatch.setattr(worker, "run_command", run)
    monkeypatch.setattr(os, "execv", lambda *_: pytest.fail("Updater must not replace the daemon"))
    if fail:
        with pytest.raises(RuntimeError):
            worker.execute(path)
    else:
        worker.execute(path)
    assert calls[0] == [sys.executable, "-m", "pip", "install", "--upgrade", "axonx", "axonx-studio"]
    assert json.loads(path.read_text())["phase"] == ("failed" if fail else "starting")


def test_git_update_preserves_untracked_files_and_refuses_conflicts(tmp_path, monkeypatch):
    remote, author, checkout = (tmp_path / name for name in ("remote.git", "author", "checkout"))

    def git(*args, cwd=None):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()

    git("init", "--bare", str(remote))
    git("init", "-b", "main", str(author))
    git("config", "user.email", "test@example.test", cwd=author)
    git("config", "user.name", "Test", cwd=author)
    (author / "source.py").write_text("value = 1\n")
    git("add", ".", cwd=author)
    git("commit", "-m", "initial", cwd=author)
    git("remote", "add", "origin", str(remote), cwd=author)
    git("push", "-u", "origin", "main", cwd=author)
    git("clone", "-b", "main", str(remote), str(checkout))
    (checkout / "local.cron").write_text("# keep local settings")
    (author / "source.py").write_text("value = 2\n")
    git("commit", "-am", "update", cwd=author)
    git("push", cwd=author)
    path = make_record(tmp_path, "git")
    path.with_name("plan.json").write_text(
        json.dumps({"cwd": str(checkout), "repository": str(checkout), "verification": "pass"})
    )
    run = worker.run_command
    monkeypatch.setattr(worker, "run_command", lambda argv, *args: run(argv, *args) if argv[0] == "git" else "")
    worker.execute(path)
    assert (checkout / "source.py").read_text() == "value = 2\n"
    assert (checkout / "local.cron").read_text() == "# keep local settings"
    (checkout / "source.py").write_text("value = 'local edit'\n")
    (author / "source.py").write_text("value = 3\n")
    git("commit", "-am", "conflict", cwd=author)
    git("push", cwd=author)
    with pytest.raises(RuntimeError, match="fetching failed"):
        worker.execute(path)
    assert (checkout / "source.py").read_text() == "value = 'local edit'\n"
    assert json.loads(path.read_text())["phase"] == "failed"


def test_restart_worker_needs_no_installation_tools(tmp_path, monkeypatch):
    path = make_record(tmp_path, "restart")
    monkeypatch.setattr(worker, "run_command", lambda *_: pytest.fail("Restart must not update"))
    worker.execute(path)
    assert json.loads(path.read_text())["phase"] == "starting"


@pytest.mark.parametrize("timeout", [False, True])
def test_command_cleanup_kills_only_its_owned_descendants(tmp_path, timeout):
    pid_file = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time,pathlib; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); time.sleep({60 if timeout else 0.1})"
    )
    with (tmp_path / "command.log").open("w") as log:
        if timeout:
            with pytest.raises(subprocess.TimeoutExpired):
                worker.run_command([sys.executable, "-c", code], str(tmp_path), log, timeout=0.5)
        else:
            worker.run_command([sys.executable, "-c", code], str(tmp_path), log, timeout=0.5)
    child = int(pid_file.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = subprocess.run(["ps", "-p", str(child), "-o", "stat="], capture_output=True, text=True, check=False)
        if result.returncode or result.stdout.strip().startswith("Z"):
            break
        time.sleep(0.05)
    else:
        os.kill(child, 9)
        pytest.fail("Updater command left a live descendant")


def test_interruption_records_failure_without_restart(tmp_path, monkeypatch):
    path = make_record(tmp_path)
    monkeypatch.setattr(worker, "run_command", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        worker.execute(path)
    assert json.loads(path.read_text())["error"] == "KeyboardInterrupt"


def test_pip_preflight_allows_missing_studio_and_rejects_editable_source(tmp_path, monkeypatch):
    from importlib import metadata, util
    from types import SimpleNamespace

    _, updater = application(tmp_path)
    updater.app_context.service.startup_directory = tmp_path
    installed = tmp_path / "site"
    editable = False

    def distribution(name):
        if name == "axonx-studio":
            raise metadata.PackageNotFoundError(name)
        return SimpleNamespace(
            read_text=lambda file: (
                '{"dir_info":{"editable":true}}'
                if editable and file == "direct_url.json"
                else "Wheel-Version: 1.0" if file == "WHEEL" else None
            ),
            locate_file=lambda name: installed / name,
        )

    monkeypatch.setattr(metadata, "distribution", distribution)
    monkeypatch.setattr(
        util,
        "find_spec",
        lambda name: SimpleNamespace(origin=installed / name / "__init__.py") if name == "axonx" else None,
    )
    assert updater._plan("pip", updater.app_context.service)["cwd"]
    editable = True
    with pytest.raises(ValueError, match="Source installations"):
        updater._plan("pip", updater.app_context.service)
