"""Exercise shutdown with real signals, workers and cancellation-resistant I/O."""

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import psutil
import pytest

from axonx.components.service import HttpService
from axonx.config import ConfigResolver
from axonx.core import Application
from axonx.utils.async_work import run_blocking


@pytest.mark.parametrize("during_launch", [False, True])
async def test_workers_stop_before_cancellation_resistant_component_cleanup(tmp_path, monkeypatch, during_launch):
    create_process = asyncio.create_subprocess_exec
    spawning, launch = asyncio.Event(), asyncio.Event()
    workers = []

    async def sleeping_worker(*_args, **kwargs):
        spawning.set()
        await launch.wait()
        process = await create_process(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        workers.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeping_worker)
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local", "force_polling": True}},
            "task_manager": {"default": {"backend": "local", "terminate_grace_seconds": 0.1}},
        },
    )
    entered, release = Event(), Event()

    class BlockedCleanup:
        async def close(self):
            def blocked_io():
                entered.set()
                release.wait(10)

            await run_blocking(blocked_io)

    closing = None
    try:
        await app.start()
        manager = app.context.components["task_manager"]["default"]
        submitting = asyncio.create_task(manager.submit(["--task", "demo", "--x", "1", "--y", "2"]))
        await asyncio.wait_for(spawning.wait(), timeout=2)
        if during_launch:
            app.request_shutdown()
        launch.set()
        handle = await asyncio.wait_for(submitting, timeout=2)
        worker = workers[0]
        app._started.append(BlockedCleanup())
        closing = asyncio.create_task(app.close())
        assert await asyncio.to_thread(entered.wait, 2)
        assert await asyncio.wait_for(worker.wait(), timeout=2) == -signal.SIGTERM
        assert not closing.done()
        with pytest.raises(RuntimeError, match="stopping"):
            await manager.submit(["--task", "demo", "--x", "1", "--y", "2"])
        release.set()
        await asyncio.wait_for(closing, timeout=3)
        status = await manager.get_status(handle.task_id)
        assert status.state == "cancelled"
    finally:
        launch.set()
        release.set()
        if closing is not None:
            await closing
        await app.close()


@pytest.mark.parametrize("force", [False, True])
async def test_shutdown_request_error_does_not_skip_other_managers_or_cleanup(tmp_path, monkeypatch, force):
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local", "force_polling": True}},
            "task_manager": {name: {"backend": "local"} for name in ("first", "second")},
        },
    )
    await app.start()
    first, second = app.context.components["task_manager"].values()
    monkeypatch.setattr(first, "request_shutdown", Mock(side_effect=RuntimeError("stop failed")))
    requested = Mock(wraps=second.request_shutdown)
    monkeypatch.setattr(second, "request_shutdown", requested)
    if force:
        with pytest.raises(ExceptionGroup, match="Task manager shutdown requests failed"):
            app.request_shutdown(force=True)
        requested.assert_called_once_with(force=True)
        requested.reset_mock()
    with pytest.raises(ExceptionGroup, match="Application cleanup failed") as error:
        await app.close()
    assert "stop failed" in str(error.value.exceptions[0].exceptions[0])
    requested.assert_called_once_with(force=False)
    assert not first.is_started and not second.is_started and not app.is_started
    await app.close()


SERVICE_SCRIPT = """
import asyncio
import signal
import sys
import threading
from pathlib import Path

from axonx.components.base import BaseComponent
from axonx.components.registry import provider
from axonx.components.task_manager.base import BaseTaskManager
from axonx.core import Application
from axonx.enums import ComponentEnum
from axonx.utils.async_work import run_blocking

root, mode, foreign_pid, port = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4])

@provider("blocked_cleanup")
class BlockedCleanup(BaseComponent):
    component_type = ComponentEnum.SYNC

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.depend("manager", "default", BaseTaskManager)

    async def _start(self):
        manager = self.get_component("task_manager")
        if mode == "hook_error":
            stop = manager.request_shutdown

            def request_shutdown(*, force=False):
                if not force:
                    raise RuntimeError("stop hook failed")
                stop(force=force)

            manager.request_shutdown = request_shutdown
        code = (
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(60)"
        )
        if mode in {"descendant", "normal_descendant"}:
            code = (
                "import subprocess,sys,time; "
                f"child=subprocess.Popen([sys.executable, '-c', {code!r}], stdout=subprocess.PIPE); "
                "child.stdout.readline(); print(child.pid, flush=True); time.sleep(60)"
            )
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            start_new_session=True, stdout=asyncio.subprocess.PIPE,
        )
        ready = await process.stdout.readline()
        if mode in {"descendant", "normal_descendant"}:
            (root / "descendant").write_bytes(ready)
        manager._supervisor.processes[process.pid] = process
        manager._supervisor.run_pids["owned"] = process.pid
        monitor = asyncio.create_task(manager._supervisor._monitor(process, "base#demo#owned", "demo", "owned"))
        manager._supervisor.monitors.add(monitor)
        monitor.add_done_callback(manager._supervisor.monitors.discard)
        # A shared record with a foreign PID must not become a kill target.
        from axonx.task.schemas.lifecycle import TaskMetadata
        from axonx.task.storage.workspace import task_path, write_task_metadata
        foreign = TaskMetadata(version=1, task_id="base#demo#foreign", run_id="foreign",
                               task_type="base", state="running", pid=foreign_pid)
        directory = task_path(root, foreign.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        write_task_metadata(directory, foreign)
        (root / "worker").write_text(str(process.pid))

    async def _close(self):
        (root / "closing").touch()
        if mode == "blocked_loop":
            import time
            time.sleep(60)
        elif mode not in {"normal", "normal_descendant"}:
            await run_blocking(threading.Event().wait)

app = Application(
    providers=[BlockedCleanup], workspace_dir=str(root), enable_logo=False,
    log_to_console=False, log_to_file=False,
    components={
        "task_repository": {"default": {"backend": "local", "force_polling": True}},
        "task_manager": {"default": {"backend": "local", "terminate_grace_seconds": 0.1}},
        "sync": {"blocked": {"backend": "blocked_cleanup"}},
    },
    service={"backend": "http", "host": "127.0.0.1", "port": port,
             "web_enabled": False,
             "cleanup_timeout": 2 if mode in {"deadline", "blocked_loop", "sigterm", "descendant", "hook_error"}
                                else 30},
)
app.context.service.run_app(app)
"""


def wait_for_file(path, process, timeout=15):
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert process.poll() is None, "Service exited before the expected shutdown stage"
        assert time.monotonic() < deadline, f"Timed out waiting for {path.name}"
        time.sleep(0.02)


def assert_process_stopped(pid, timeout=2):
    deadline = time.monotonic() + timeout
    while True:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return
        except psutil.NoSuchProcess:
            return
        assert time.monotonic() < deadline, f"Process {pid} survived shutdown"
        time.sleep(0.02)


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "deadline",
        "second_interrupt",
        "blocked_loop",
        "sigterm",
        "descendant",
        "normal_descendant",
        "hook_error",
    ],
)
def test_service_signals_bound_cleanup_and_kill_only_owned_workers(tmp_path, mode):
    script = tmp_path / "service.py"
    script.write_text(SERVICE_SCRIPT)
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    worker_pid = None
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True) as foreign,
        (tmp_path / "output.log").open("w+") as output,
    ):
        with subprocess.Popen(
            [sys.executable, str(script), str(tmp_path), mode, str(foreign.pid), str(port)],
            env=environment,
            stdout=output,
            stderr=output,
            start_new_session=True,
        ) as service:
            try:
                wait_for_file(tmp_path / "worker", service)
                worker_pid = int((tmp_path / "worker").read_text())
                # Startup writes the worker file before Uvicorn installs all runtime state.
                deadline = time.monotonic() + 15
                while "Application startup complete" not in (tmp_path / "output.log").read_text():
                    assert service.poll() is None
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
                started = time.monotonic()
                service.send_signal(signal.SIGTERM if mode == "sigterm" else signal.SIGINT)
                wait_for_file(tmp_path / "closing", service)
                if mode == "second_interrupt":
                    service.send_signal(signal.SIGINT)
                service.wait(timeout=8)
                assert time.monotonic() - started < 8
                assert foreign.poll() is None
                assert os.get_blocking(output.fileno())
                assert_process_stopped(worker_pid)
                if (tmp_path / "descendant").exists():
                    assert_process_stopped(int((tmp_path / "descendant").read_text()))
                text = (tmp_path / "output.log").read_text()
                if mode in {"normal", "normal_descendant"}:
                    assert "forcing shutdown" not in text
                    assert "Application shutdown complete" in text
                else:
                    assert service.returncode == 130
                    assert "forcing shutdown" in text
            finally:
                if service.poll() is None:
                    service.kill()
                    service.wait(timeout=5)
                if worker_pid is not None:
                    try:
                        os.killpg(worker_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                foreign.kill()
                foreign.wait(timeout=5)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_cleanup_deadline_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError, match="cleanup_timeout"):
        HttpService(cleanup_timeout=timeout)


@pytest.mark.parametrize("source", ["default", "remote"])
def test_cleanup_timeout_configuration_and_environment_override(tmp_path, monkeypatch, source):
    monkeypatch.delenv("AXONX_SERVICE_CLEANUP_TIMEOUT", raising=False)
    monkeypatch.setenv("AXONX_TARGET", "192.0.2.10:1024")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "test-token")
    resolver = ConfigResolver()
    assert resolver.load(source)["service"]["cleanup_timeout"] == 15
    monkeypatch.setenv("AXONX_SERVICE_CLEANUP_TIMEOUT", "0.5")
    assert resolver.load(source)["service"]["cleanup_timeout"] == 0.5
    config = tmp_path / "custom.yaml"
    config.write_text(f"extends: {source}\nservice:\n  cleanup_timeout: 3\n")
    assert resolver.load(config)["service"]["cleanup_timeout"] == 3
