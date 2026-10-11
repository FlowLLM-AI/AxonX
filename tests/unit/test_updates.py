"""Self-update admission and standalone process handoff regression tests."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from axonx.components.updater.manager import RESPONSE_CALLBACKS
from axonx.components.updater import worker
from axonx.config import resolve_app_config
from axonx.core import Application
from axonx.plugin_kit.environment import environment_operation


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
    service = app.context.service
    service.server = SimpleNamespace(started=True, should_exit=False)
    service.restart_arguments = ["start"]
    return app, app.context.components["updater"]["default"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("job", ["update_from_pip", "restart_service"])
async def test_update_response_precedes_shutdown_and_blocks_mutations(tmp_path, monkeypatch, stream, job):
    app, updater = application(tmp_path)
    monkeypatch.setattr(updater, "_plan", lambda mode, service: {"cwd": str(tmp_path), "arguments": ["start"]})
    server = app.context.service.build_service(app)
    transport = httpx.ASGITransport(app=server)
    sent = []

    async def send(message):
        assert not app.context.service.server.should_exit
        sent.append(message)

    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": "Bearer secret"}
        ) as client:
            # Wrap ASGI sends to verify all response bytes precede shutdown.
            original = transport.app

            async def wrapped(scope, receive, output):
                async def observed(message):
                    await send(message)
                    await output(message)

                await original(scope, receive, observed)

            transport.app = wrapped
            url = "/jobs/" + job + ("/events" if stream else "")
            response = await client.post(url, json={"arguments": {}})
            assert response.status_code == 200
            assert sent[-1]["type"] == "http.response.body"
            assert app.context.service.server.should_exit
            assert updater.pending.is_file()
            assert updater.pending.with_name("worker.py").is_file()
            transport.app = original
            status = await client.post("/jobs/get_update_status", json={"arguments": {}})
            assert status.json()["answer"]["record"]["phase"] == "accepted"
            assert (await client.post("/jobs/update_from_git", json={"arguments": {}})).status_code == 422

            @environment_operation
            async def mutation(component):
                pytest.fail("Maintenance must block environment mutation")

            with pytest.raises(RuntimeError, match="maintenance"):
                await mutation(updater)


@pytest.mark.asyncio
async def test_unauthenticated_service_hides_updates(tmp_path):
    app, _ = application(tmp_path, token=None)
    server = app.context.service.build_service(app)
    async with app:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
            catalog = (await client.get("/jobs")).json()["answer"]["items"]
            assert not any(item["name"].startswith("update_") for item in catalog)
            assert (await client.post("/jobs/update_from_git", json={"arguments": {}})).status_code == 404
            assert (await client.post("/jobs/restart_service", json={"arguments": {}})).status_code == 404


@pytest.mark.asyncio
async def test_preflight_failure_does_not_cancel_tasks(tmp_path, monkeypatch):
    app, updater = application(tmp_path)

    monkeypatch.setattr(updater, "_plan", lambda *_: (_ for _ in ()).throw(ValueError("bad installation")))
    token = RESPONSE_CALLBACKS.set([])
    try:
        with pytest.raises(ValueError, match="bad installation"):
            await updater.request("git", force=True)
        assert updater.pending is None
        assert not app.context.metadata.get("maintenance")
    finally:
        RESPONSE_CALLBACKS.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["pip", "restart"])
async def test_active_tasks_and_forced_cancellation(tmp_path, monkeypatch, mode):
    app, updater = application(tmp_path)
    active = SimpleNamespace(state=SimpleNamespace(is_terminal=False), task_id="demo", run_id="run")
    cancelled = []

    async def statuses():
        return [active]

    async def cancel(**kwargs):
        cancelled.append(kwargs)
        return True

    # Inject a fake configured manager without constructing research workers.
    app.context._components["task_manager"] = {"default": SimpleNamespace(list_statuses=statuses, cancel=cancel)}
    monkeypatch.setattr(updater, "_plan", lambda *_: {})
    token = RESPONSE_CALLBACKS.set([])
    try:
        with pytest.raises(RuntimeError, match="Active Tasks"):
            await updater.request(mode)
        assert not cancelled
        record = await updater.request(mode, force=True)
        assert record["phase"] == "accepted"
        assert cancelled == [{"task_id": "demo", "run_id": "run"}]
    finally:
        RESPONSE_CALLBACKS.reset(token)


@pytest.mark.asyncio
async def test_interrupted_update_and_status_path_validation(tmp_path):
    _, updater = application(tmp_path)
    folder = updater.directory / ("a" * 32)
    folder.mkdir(parents=True)
    worker.save(folder / "record.json", {"phase": "building"})
    await updater.start()
    assert updater.status()["record"]["phase"] == "failed"
    with pytest.raises(ValueError, match="Invalid update_id"):
        updater.status("../record.json")
    await updater.close()


class ReplacedProcess(BaseException):
    """Stop a mocked exec without being treated as an update failure."""


def make_record(tmp_path, mode="pip"):
    path = tmp_path / "record.json"
    worker.save(path, {"mode": mode, "phase": "accepted", "before": {}, "error": None})
    (tmp_path / "plan.json").write_text(
        json.dumps({"cwd": str(tmp_path), "arguments": ["start", "--port", "9876"], "verification": "pass"}),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("fail", [False, True])
def test_worker_preserves_restart_command_and_records_install_failure(tmp_path, monkeypatch, fail):
    path = make_record(tmp_path)
    calls = []

    def run(argv, *_):
        calls.append(argv)
        if fail:
            raise subprocess.CalledProcessError(1, argv)
        return "output"

    def restart(executable, argv):
        assert executable == sys.executable
        assert argv == [sys.executable, "-m", "axonx.cli", "start", "--port", "9876"]
        assert worker.os.environ[worker.RECORD_ENV] == str(path)
        raise ReplacedProcess

    monkeypatch.setattr(worker, "run_command", run)
    monkeypatch.setattr(worker.os, "execv", restart)
    monkeypatch.setattr(worker.os, "chdir", lambda _: None)
    monkeypatch.setenv(worker.RECORD_ENV, "")
    with pytest.raises(ReplacedProcess):
        worker.execute(path)
    record = json.loads(path.read_text())
    assert record["phase"] == ("failed" if fail else "starting")
    assert calls[0] == [sys.executable, "-m", "pip", "install", "--upgrade", "axonx", "axonx-studio"]
    worker.finish_startup()
    assert json.loads(path.read_text())["phase"] == ("failed" if fail else "succeeded")


@pytest.mark.parametrize("fail", [False, True])
def test_restart_worker_skips_all_commands_and_retains_startup(tmp_path, monkeypatch, fail):
    path = make_record(tmp_path, "restart")
    monkeypatch.setattr(worker, "run_command", lambda *_: pytest.fail("Restart must not run Git, npm or pip"))
    directories = []
    monkeypatch.setattr(worker.os, "chdir", directories.append)

    def restart(executable, argv):
        assert executable == sys.executable
        assert argv == [sys.executable, "-m", "axonx.cli", "start", "--port", "9876"]
        if fail:
            raise OSError("cannot exec")
        raise ReplacedProcess

    monkeypatch.setattr(worker.os, "execv", restart)
    monkeypatch.setenv(worker.RECORD_ENV, "")
    with pytest.raises(OSError if fail else ReplacedProcess):
        worker.execute(path)
    assert directories == [str(tmp_path)]
    record = json.loads(path.read_text())
    assert record["phase"] == ("failed" if fail else "starting")
    assert record["error"] == ("Restart failed: cannot exec" if fail else None)
    worker.finish_startup()
    assert json.loads(path.read_text())["phase"] == ("failed" if fail else "succeeded")


def test_restart_plan_requires_no_source_or_build_tools(tmp_path, monkeypatch):
    _, updater = application(tmp_path)
    service = updater.app_context.service
    service.startup_directory = tmp_path
    service.restart_arguments = ["start", "--service.port", "1025"]
    monkeypatch.setattr("axonx.components.updater.manager.shutil.which", lambda *_: None)
    monkeypatch.setattr(subprocess, "check_output", lambda *_args, **_kwargs: pytest.fail("No Git preflight"))
    plan = updater._plan("restart", service)
    assert plan["cwd"] == str(tmp_path)
    assert plan["arguments"] == service.restart_arguments
    assert set(plan) == {"cwd", "arguments"}


def test_startup_failure_is_not_success(tmp_path, monkeypatch):
    path = make_record(tmp_path)
    worker.save(path, {"phase": "starting"})
    monkeypatch.setenv(worker.RECORD_ENV, str(path))
    worker.finish_startup("Cannot bind port")
    record = json.loads(path.read_text())
    assert record["phase"] == "failed"
    assert record["error"] == "Cannot bind port"


@pytest.mark.parametrize("collision", [False, True])
def test_git_worker_discards_source_and_retains_runtime(tmp_path, monkeypatch, collision):
    repository = tmp_path / "repo"
    repository.mkdir()

    def git(*args, cwd=repository):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.test")
    git("config", "user.name", "Test")
    (repository / "source.py").write_text("original")
    (repository / ".gitignore").write_text(".venv/\n.env\n")
    (repository / "axonx_studio").mkdir()
    (repository / "axonx_studio" / "package.json").write_text("{}")
    git("add", ".")
    git("commit", "-m", "initial")
    origin = tmp_path / "origin.git"
    git("clone", "--bare", str(repository), str(origin), cwd=tmp_path)
    git("remote", "add", "origin", str(origin))
    (repository / "source.py").write_text("dirty")
    (repository / "untracked.py").write_text("discard")
    for folder in (".venv", "runtime"):
        (repository / folder).mkdir()
        (repository / folder / "keep").write_text("retain")
    (repository / ".env").write_text("retain")
    if collision:
        upstream = tmp_path / "upstream"
        git("clone", str(origin), str(upstream), cwd=tmp_path)
        git("config", "user.email", "test@example.test", cwd=upstream)
        git("config", "user.name", "Test", cwd=upstream)
        (upstream / ".venv").mkdir()
        (upstream / ".venv" / "keep").write_text("overwrite")
        git("add", "-f", ".venv/keep", cwd=upstream)
        git("commit", "-m", "colliding runtime", cwd=upstream)
        git("push", "origin", "main", cwd=upstream)
    path = make_record(tmp_path, "git")
    plan = json.loads(path.with_name("plan.json").read_text())
    plan.update(
        cwd=str(repository),
        repository=str(repository),
        protected=["runtime", ".venv", ".env"],
        excludes=["-e", "/runtime"],
    )
    path.with_name("plan.json").write_text(json.dumps(plan))
    original_run = worker.run_command

    def run(argv, *args):
        if argv[0] == "git":
            return original_run(argv, *args)
        return ""

    monkeypatch.setattr(worker, "run_command", run)
    monkeypatch.setattr(worker.os, "execv", lambda *_: (_ for _ in ()).throw(ReplacedProcess()))
    monkeypatch.setattr(worker.os, "chdir", lambda _: None)
    monkeypatch.setenv(worker.RECORD_ENV, "")
    with pytest.raises(ReplacedProcess):
        worker.execute(path)
    assert (repository / "source.py").read_text() == ("dirty" if collision else "original")
    assert (repository / "untracked.py").exists() == collision
    assert (repository / ".env").exists()
    assert (repository / ".venv" / "keep").exists()
    assert (repository / "runtime" / "keep").exists()
    assert json.loads(path.read_text())["phase"] == ("failed" if collision else "starting")


@pytest.mark.asyncio
async def test_mcp_update_returns_acceptance_before_shutdown(tmp_path, monkeypatch):
    import asyncio
    import socket

    import uvicorn

    from axonx.components.client import McpClient

    app, updater = application(tmp_path)
    monkeypatch.setattr(updater, "_plan", lambda *_: {})
    server_app = app.context.service.build_service(app)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(server_app, log_level="error"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.01)
            async with McpClient(target=f"127.0.0.1:{listener.getsockname()[1]}", token="secret") as client:
                result = await client.run_job("update_from_pip")
                assert result.success, result.answer
                assert result.answer["phase"] == "accepted"
                while not app.context.service.server.should_exit:
                    await asyncio.sleep(0.01)
    finally:
        server.should_exit = True
        await task
        listener.close()


@pytest.mark.parametrize("updater_name", ["default", "custom"])
@pytest.mark.parametrize("job", ["update_from_pip", "restart_service"])
def test_real_service_reexec_retains_pid_and_reports_ready(tmp_path, updater_name, job):
    """Exercise actual CLI -> updater -> CLI execs with package mutations replaced."""
    import os
    import socket
    import time
    import urllib.error
    import urllib.request

    import yaml

    from axonx import __file__ as source_file

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    defaults = resolve_app_config(log_config=False)
    config = {
        "workspace_dir": str(tmp_path / "runtime"),
        "log_dir": str(tmp_path / "logs"),
        "log_to_file": False,
        "enable_logo": False,
        "components": {"updater": {updater_name: {"backend": "local"}}},
        "jobs": {name: defaults["jobs"][name] for name in (job, "get_update_status")},
        "service": {"backend": "http", "host": "127.0.0.1", "port": port, "token": "secret", "web_enabled": False},
    }
    for job_config in config["jobs"].values():
        job_config["steps"][0]["updater"] = updater_name
    config_path = tmp_path / "service.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text(
        """import sys
from pathlib import Path
from axonx.cli import main
from axonx.components.updater import manager

original_copy = manager.shutil.copyfile
def snapshot(source, destination):
    result = original_copy(source, destination)
    path = Path(destination)
    script = path.read_text()
    script = script.replace('if __name__ ==', """
        + repr("""_run = run_command

def fake_install(argv, *args):
    if argv[1:3] == ["-m", "pip"]:
        return "simulated install"
    return _run(argv, *args)

run_command = fake_install
if __name__ ==""")
        + """)
    path.write_text(script)
    return result
manager.shutil.copyfile = snapshot
original_plan = manager.UpdateManager._plan
def plan(self, mode, service):
    if mode == "restart":
        return original_plan(self, mode, service)
    return {
        'cwd': str(service.startup_directory), 'arguments': service.restart_arguments,
        'verification': 'import axonx',
    }
manager.UpdateManager._plan = plan
raise SystemExit(main(['start', '--config', sys.argv[1]]))
""",
        encoding="utf-8",
    )
    repository = str(Path(source_file).resolve().parent.parent)
    environment = {**os.environ, "PYTHONPATH": repository}
    # Do not propagate a marker from another test or from a real service.
    environment.pop(worker.RECORD_ENV, None)
    output = tmp_path / "server.log"

    def request(job):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/jobs/{job}",
            data=b'{"arguments":{}}',
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1) as response:
            return json.load(response)

    with (
        output.open("w", encoding="utf-8") as log,
        subprocess.Popen(
            [sys.executable, str(bootstrap), str(config_path)], cwd=tmp_path, env=environment, stdout=log, stderr=log
        ) as process,
    ):
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert process.poll() is None, output.read_text()
                try:
                    accepted = request(job)
                    break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.05)
            else:
                pytest.fail(output.read_text())
            assert accepted["success"], accepted
            assert accepted["answer"]["phase"] == "accepted"
            while time.monotonic() < deadline:
                assert process.poll() is None, output.read_text()
                try:
                    status = request("get_update_status")["answer"]["record"]
                    if status and status["phase"] == "succeeded":
                        assert status["update_id"] == accepted["answer"]["update_id"]
                        break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    pass
                time.sleep(0.05)
            else:
                pytest.fail(output.read_text())
            assert process.poll() is None  # The original PID survived both exec transitions.
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_git_plan_protects_runtime_without_excluding_source_subdirectory(tmp_path, monkeypatch):
    from axonx.components.updater import manager

    app, updater = application(tmp_path)
    repository = tmp_path / "source"
    (repository / "axonx").mkdir(parents=True)
    (repository / "axonx_studio").mkdir()
    source = repository / "axonx" / "__init__.py"
    source.write_text("")
    (repository / "axonx_studio" / "package.json").write_text("{}")
    subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.test", "-c", "user.name=Test", "commit", "-m", "initial"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(manager, "__file__", str(source.parent / "components" / "updater" / "manager.py"))
    app.context.service.startup_directory = repository / "axonx_studio"
    app.app_config.workspace_dir = str(repository / "runtime" / "research")
    plan = updater._plan("git", app.context.service)
    assert plan["repository"] == str(repository)
    assert "/runtime" in plan["excludes"]
    assert "axonx_studio" not in plan["excludes"]
    local_config = repository / "settings" / "service.yaml"
    local_config.parent.mkdir()
    local_config.write_text("extends: default")
    app.context.service.configuration_paths = {local_config, repository / "axonx_studio" / "package.json"}
    linked_runtime = repository / "linked-runtime"
    external_runtime = tmp_path / "external-runtime"
    external_runtime.mkdir()
    linked_runtime.symlink_to(external_runtime, target_is_directory=True)
    app.app_config.workspace_dir = str(linked_runtime)
    plan = updater._plan("git", app.context.service)
    assert "/linked-runtime" in plan["excludes"]
    assert "/settings/service.yaml" in plan["excludes"]
    assert "axonx_studio/package.json" not in plan["protected"]
    disposable = local_config.parent / "discard.py"
    disposable.write_text("discard")
    subprocess.run(["git", "clean", "-fd", *plan["excludes"]], cwd=repository, check=True, capture_output=True)
    assert linked_runtime.is_symlink()
    assert local_config.read_text() == "extends: default"
    assert not disposable.exists()
    app.app_config.workspace_dir = str(repository / "axonx")
    with pytest.raises(ValueError, match="tracked source"):
        updater._plan("git", app.context.service)
    subprocess.run(["git", "rm", "--cached", "axonx/__init__.py"], cwd=repository, check=True, capture_output=True)
    with pytest.raises(ValueError, match="tracked source"):
        updater._plan("git", app.context.service)
    app.app_config.workspace_dir = str(repository)
    with pytest.raises(ValueError, match="repository root"):
        updater._plan("git", app.context.service)


def test_pip_plan_does_not_mistake_ancestor_directory_for_import_shadow(tmp_path, monkeypatch):
    from axonx.components.updater import manager
    from importlib import metadata

    app, updater = application(tmp_path)
    monkeypatch.setattr(manager, "__file__", str(tmp_path / "site" / "axonx" / "components" / "updater" / "manager.py"))

    def distribution(name):
        return SimpleNamespace(
            read_text=lambda file: "Wheel-Version: 1.0" if file == "WHEEL" else None,
            locate_file=lambda file: tmp_path / "site" / file,
        )

    from importlib import util

    monkeypatch.setattr(util, "find_spec", lambda _: None)
    monkeypatch.setattr(metadata, "distribution", distribution)
    app.context.service.startup_directory = tmp_path
    assert updater._plan("pip", app.context.service)["cwd"] == str(tmp_path)
    app.context.service.startup_directory = tmp_path / "site"
    with pytest.raises(ValueError, match="shadows"):
        updater._plan("pip", app.context.service)
    app.context.service.startup_directory = tmp_path
    monkeypatch.setattr(
        manager, "__file__", str(tmp_path / "other-source" / "axonx" / "components" / "updater" / "manager.py")
    )
    with pytest.raises(ValueError, match="Source imports shadow"):
        updater._plan("pip", app.context.service)


def test_failed_executor_handoff_is_durable(tmp_path, monkeypatch):
    _, updater = application(tmp_path)
    updater.pending = make_record(tmp_path)
    monkeypatch.setattr(worker.os, "execv", lambda *_: (_ for _ in ()).throw(OSError("Cannot execute")))
    with pytest.raises(OSError, match="Cannot execute"):
        updater.handoff()
    assert json.loads(updater.pending.read_text())["phase"] == "failed"


@pytest.mark.parametrize("timeout", [False, True])
def test_command_cleanup_kills_descendants(tmp_path, timeout):
    import os
    import time

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


def test_configuration_resolver_tracks_inherited_files(tmp_path):
    from axonx.config import ConfigResolver

    parent = tmp_path / "parent.yaml"
    parent.write_text("language: zh")
    child = tmp_path / "child.yaml"
    child.write_text("extends: parent.yaml")
    resolver = ConfigResolver()
    assert resolver.load(child)["language"] == "zh"
    assert {child.resolve(), parent.resolve()} <= resolver.loaded_paths
    resolver.load("default")
    assert child.resolve() not in resolver.loaded_paths


def test_protected_paths_detect_ancestors_and_unicode():
    with pytest.raises(ValueError, match="tracked source"):
        worker.check_protected_paths("运行数据/credentials\0", ["运行数据"])
    with pytest.raises(ValueError, match="tracked source"):
        worker.check_protected_paths("settings\0", ["settings/service.yaml"])


def test_interruption_records_failure_without_restarting(tmp_path, monkeypatch):
    path = make_record(tmp_path)
    monkeypatch.setattr(worker, "run_command", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(worker.os, "execv", lambda *_: pytest.fail("An interrupted updater must not restart itself"))
    with pytest.raises(KeyboardInterrupt):
        worker.execute(path)
    record = json.loads(path.read_text())
    assert record["phase"] == "failed"
    assert record["error"] == "KeyboardInterrupt"
