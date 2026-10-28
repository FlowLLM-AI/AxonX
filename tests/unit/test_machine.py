"""Exercise machine components, vendor parsing and bounded Python execution."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from axonx.app.components.base import BaseComponent
from axonx.app.components.job.command import run_command
from axonx.app.components.machine import build_info, gpu, local
from axonx.app.components.machine.base import BaseMachineComponent
from axonx.app.components.machine.local import LocalMachineComponent
from axonx.app.components.machine.models import BuildInfo, GpuInfo, PythonOutput
from axonx.app.components.machine.python import MAX_OUTPUT_BYTES, run_python
from axonx.app.components.registry import provider
from axonx.app.config.models import TargetConfig
from axonx.app.core.application import Application


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
async def test_python_execution_rejects_invalid_timeouts_before_spawning(timeout):
    with pytest.raises(ValueError, match="timeout must be finite and positive"):
        await run_python("raise AssertionError('must not execute')", timeout)


@pytest.mark.parametrize("timeout", [True, None, "1"])
async def test_python_execution_rejects_nonnumeric_timeouts(timeout):
    with pytest.raises(TypeError, match="timeout must be a number"):
        await run_python("raise AssertionError('must not execute')", timeout)


def test_build_identity_queries_the_checkout_containing_the_package(monkeypatch):
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="revision\n")

    monkeypatch.setattr(build_info.subprocess, "run", run)
    assert build_info._git("rev-parse", "HEAD") == "revision"
    assert commands == [["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"]]


@pytest.mark.parametrize("exit_code", [0, 3])
async def test_python_execution_captures_both_streams_and_exit_status(exit_code):
    output = await run_python(f"import sys; print('out'); print('error', file=sys.stderr); sys.exit({exit_code})", 5)
    assert output.stdout == "out\n"
    assert output.stderr == "error\n"
    assert output.exit_code == exit_code


@pytest.mark.asyncio
async def test_python_execution_reports_timeout_and_reaps_the_process():
    output = await run_python("import os, time; print(os.getpid()); time.sleep(60)", 0.5)
    assert output.exit_code is None
    assert "timed out" in output.stderr
    with pytest.raises(ProcessLookupError):
        os.kill(int(output.stdout), 0)


async def test_python_execution_bounds_each_output_stream():
    output = await run_python(
        f"import sys; sys.stdout.write('x' * {MAX_OUTPUT_BYTES + 100}); "
        f"sys.stderr.write('y' * {MAX_OUTPUT_BYTES + 100})",
        5,
    )
    assert output.exit_code == 0
    assert output.stdout == "x" * MAX_OUTPUT_BYTES
    assert output.stderr == "y" * MAX_OUTPUT_BYTES
    assert output.stdout_truncated and output.stderr_truncated


async def test_cancelling_python_reaps_the_process(tmp_path):
    pid_file = tmp_path / "python.pid"
    task = asyncio.create_task(
        run_python(f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)", 30),
    )
    try:
        async with asyncio.timeout(5):
            while not pid_file.exists() or not pid_file.read_text():
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancelling_python_during_spawn_reaps_the_created_process(monkeypatch):
    loop = asyncio.get_running_loop()
    spawn = loop.subprocess_exec
    spawned, release = asyncio.Event(), asyncio.Event()
    process_ids = []

    async def delayed_spawn(*args, **kwargs):
        result = await spawn(*args, **kwargs)
        process_ids.append(result[0].get_pid())
        spawned.set()
        await release.wait()
        return result

    monkeypatch.setattr(loop, "subprocess_exec", delayed_spawn)
    task = asyncio.create_task(run_python("print('must not execute')", 30))
    try:
        await asyncio.wait_for(spawned.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        with pytest.raises(ProcessLookupError):
            os.kill(process_ids[0], 0)
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for pid in process_ids:
            with suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)


async def test_python_spawn_failures_propagate(monkeypatch):
    spawn = AsyncMock(side_effect=OSError("cannot spawn"))
    monkeypatch.setattr(asyncio.get_running_loop(), "subprocess_exec", spawn)
    with pytest.raises(OSError, match="cannot spawn"):
        await run_python("print('must not execute')", 5)


async def test_successful_python_execution_terminates_background_descendants():
    output = await run_python(
        "import subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "print(child.pid)",
        5,
    )
    assert output.exit_code == 0
    pid = int(output.stdout)
    try:
        async with asyncio.timeout(5):
            while local.psutil.pid_exists(pid):
                try:
                    if local.psutil.Process(pid).status() == local.psutil.STATUS_ZOMBIE:
                        break
                except local.psutil.NoSuchProcess:
                    break
                await asyncio.sleep(0.01)
    finally:
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


@pytest.fixture
def machine_app(tmp_path):
    return Application(
        workspace_dir=str(tmp_path / "missing" / "workspace"),
        log_to_console=False,
        log_to_file=False,
        components={"machine": {"default": {"backend": "local", "cpu_sample_interval": 0.2}}},
        service={"backend": "http", "token": "test-token"},
    )


async def test_local_machine_samples_off_loop_and_diagnoses_without_creating_files(machine_app, tmp_path, monkeypatch):
    intervals, threads = [], []

    def cpu_percent(interval):
        intervals.append(interval)
        threads.append(threading.get_ident())
        return 25

    monkeypatch.setattr(local.psutil, "cpu_percent", cpu_percent)
    monkeypatch.setattr(local.psutil, "cpu_count", lambda logical: 8 if logical else 4)
    monkeypatch.setattr(
        local.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=100, used=60, available=40, percent=60),
    )
    monkeypatch.setattr(local, "get_build_info", lambda: BuildInfo(version="test"))
    device = GpuInfo(vendor="nvidia", index=0)
    monkeypatch.setattr(local, "collect_gpus", lambda warn: [device])
    for name in local.CREDENTIAL_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "secret-must-not-be-returned")
    machine = machine_app.context.components["machine"]["default"]

    info = await machine.status()
    diagnostics = await machine.diagnose()
    assert info.cpu.total_cores == 8 and info.cpu.physical_cores == 4 and info.cpu.usage_percent == 25
    assert info.memory.used_bytes == 60 and info.gpus == [device]
    assert diagnostics.axonx == info.axonx and diagnostics.cpu == info.cpu and diagnostics.memory == info.memory
    assert diagnostics.workspace.path == str(machine_app.workspace.root)
    assert not diagnostics.workspace.exists and diagnostics.workspace.disk.path == str(tmp_path)
    assert not machine_app.workspace.root.parent.exists()
    assert diagnostics.python.executable == sys.executable and diagnostics.service_auth_enabled
    assert diagnostics.credentials_configured == {
        name: name == "AXONX_SERVICE_TOKEN" for name in local.CREDENTIAL_NAMES
    }
    assert "secret-must-not-be-returned" not in diagnostics.model_dump_json()
    assert intervals == [0.2, 0.2] and all(thread != threading.get_ident() for thread in threads)


@pytest.mark.parametrize("value", [True, None, "0.1", -1, float("nan"), float("inf")])
def test_machine_rejects_invalid_sample_intervals(value):
    with pytest.raises((TypeError, ValueError), match="cpu_sample_interval"):
        LocalMachineComponent(cpu_sample_interval=value)


async def test_target_health_is_concurrent_ordered_and_isolates_failures(machine_app, monkeypatch):
    machine = machine_app.context.components["machine"]["default"]
    assert await machine.list_machines() == []
    targets = [
        TargetConfig(address=f"http://{name}:1024", token=f"{name}-token") for name in ("online", "offline", "broken")
    ]
    machine_app.app_config.targets = targets
    ready = asyncio.Event()
    connections = []
    machine.logger = Mock()

    class Client:
        def __init__(self, **options):
            self.options = options
            connections.append(options)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def health(self):
            if len(connections) == len(targets):
                ready.set()
            await ready.wait()
            if "broken" in self.options["target"]:
                raise OSError("unreachable")
            return "online" in self.options["target"]

    monkeypatch.setattr(local.client, "HttpClient", Client)
    result = await asyncio.wait_for(machine.list_machines(), 5)
    assert [item.address for item in result] == [target.address for target in targets]
    assert [item.healthy for item in result] == [True, False, False]
    assert connections == [
        {"target": target.address, "token": target.token, "timeout": local.HEALTH_TIMEOUT_SECONDS} for target in targets
    ]
    machine.logger.warning.assert_called_once()


async def test_cancelling_target_health_waits_for_all_connections_to_close(machine_app, monkeypatch):
    machine = machine_app.context.components["machine"]["default"]
    machine_app.app_config.targets = [TargetConfig(address=f"http://target-{index}:1024") for index in range(2)]
    ready = asyncio.Event()
    connected, closed = [], []

    class Client:
        def __init__(self, target, **kwargs):
            self.address = target

        async def __aenter__(self):
            connected.append(self.address)
            if len(connected) == 2:
                ready.set()
            return self

        async def __aexit__(self, *args):
            await asyncio.sleep(0.01 if self.address.endswith("0:1024") else 0.05)
            closed.append(self.address)

        async def health(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(local.client, "HttpClient", Client)
    task = asyncio.create_task(machine.list_machines())
    try:
        await asyncio.wait_for(ready.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert sorted(closed) == sorted(connected)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("exit_code", [0, 2, None])
async def test_machine_steps_resolve_named_backends_and_preserve_results(tmp_path, monkeypatch, exit_code):
    @provider("alternate")
    class AlternateMachine(LocalMachineComponent):
        pass

    operations = {
        "machine_status": "status",
        "diagnose_step": "diagnose",
        "machine_list": "list_machines",
        "machine_python": "run_python",
    }
    app = Application(
        providers=(AlternateMachine,),
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={"machine": {"default": {"backend": "local"}, "selected": {"backend": "alternate"}}},
        jobs={name: {"steps": [{"backend": name, "machine": "selected"}]} for name in operations},
    )
    machine = app.context.components["machine"]["selected"]
    assert isinstance(machine, BaseMachineComponent) and isinstance(machine, BaseComponent)
    for operation in operations.values():
        result = PythonOutput(stdout="result", exit_code=exit_code) if operation == "run_python" else operation
        monkeypatch.setattr(machine, operation, AsyncMock(return_value=result))
    async with app:
        assert machine.is_started
        for job, operation in operations.items():
            response = await app.run_job(
                job, {"code": "print('result')", "timeout": 2} if operation == "run_python" else {}
            )
            if operation == "run_python":
                assert response.model_dump(mode="json")["answer"]["stdout"] == "result"
                assert response.answer.exit_code == exit_code
                assert response.success == (exit_code == 0)
                machine.run_python.assert_awaited_once_with("print('result')", 2)
            else:
                assert response.success and response.answer == operation
                getattr(machine, operation).assert_awaited_once_with()
    assert not machine.is_started


def test_gpu_parsers_normalize_vendor_units_and_missing_or_inconsistent_metrics():
    devices = gpu.parse_nvidia_output(
        '0, GPU-id, "Device, name", 8, 2, 6, 25\n'
        "malformed\n"
        "-1, invalid, ignored, 8, 2, 6, 25\n"
        "1, , , 8, 9, 10, NaN\n"
        "2, , , N/A, -1, N/A, 101\n",
    )
    assert [item.index for item in devices] == [0, 1, 2]
    assert devices[0].name == "Device, name"
    assert devices[0].memory_total_bytes == 8 * gpu.MIB_BYTES
    assert devices[0].memory_used_bytes == 2 * gpu.MIB_BYTES
    assert devices[0].memory_available_bytes == 6 * gpu.MIB_BYTES
    assert devices[0].memory_usage_percent == 25 and devices[0].usage_percent == 25
    assert devices[1].memory_used_bytes is None and devices[1].memory_available_bytes is None
    assert devices[1].memory_usage_percent is None and devices[1].usage_percent is None
    assert devices[2].memory_total_bytes is None and devices[2].memory_used_bytes is None
    assert devices[2].usage_percent is None
    amd = gpu.parse_rocm_output(
        json.dumps(
            {
                "card2": {
                    "Unique ID": "amd-id",
                    "Card model": "AMD",
                    "VRAM Total Memory (B)": 100,
                    "VRAM Total Used Memory (B)": 30,
                    "GPU use (%)": "45",
                },
                "card-1": {},
                "cardx": {},
                "other": {},
                "card3": None,
            }
        )
    )
    assert len(amd) == 1 and amd[0].index == 2 and amd[0].vendor == "amd"
    assert amd[0].memory_total_bytes == 100 and amd[0].memory_available_bytes == 70
    assert amd[0].memory_usage_percent == 30 and amd[0].usage_percent == 45


def test_gpu_parsers_ignore_numeric_overflow():
    nvidia = gpu.parse_nvidia_output("0, id, GPU, 1e308, 1e308, 1e308, 1e308")[0]
    assert nvidia.memory_total_bytes is None and nvidia.memory_used_bytes is None
    assert nvidia.memory_available_bytes is None and nvidia.usage_percent is None
    amd = gpu.parse_rocm_output(json.dumps({"card0": {"VRAM Total Memory (B)": 10**400, "GPU use (%)": 10**400}}))[0]
    assert amd.memory_total_bytes is None and amd.usage_percent is None


def test_rocm_parser_normalizes_text_and_rejects_boolean_metrics():
    device = gpu.parse_rocm_output(
        json.dumps(
            {
                "card0": {
                    "Unique ID": "  amd-id  ",
                    "Card series": ["invalid"],
                    "Card model": "  AMD  ",
                    "VRAM Total Memory (B)": True,
                    "GPU use (%)": False,
                },
            },
        ),
    )[0]
    assert device.uuid == "amd-id" and device.name == "AMD"
    assert device.memory_total_bytes is None and device.usage_percent is None


@pytest.mark.parametrize("output", ['{"error": "driver unavailable"}', '{"cardx": {}}', "[]", "invalid JSON"])
def test_rocm_parser_reports_invalid_output(output):
    with pytest.raises(ValueError):
        gpu.parse_rocm_output(output)
    assert gpu.parse_rocm_output("{}") == []


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired("nvidia-smi", 5),
        subprocess.CalledProcessError(1, "nvidia-smi", stderr="driver\nfailed"),
        OSError("unavailable"),
        "invalid output",
    ],
)
def test_gpu_probe_failures_preserve_other_vendors(monkeypatch, failure):
    monkeypatch.setattr(gpu.platform, "system", lambda: "Linux")
    monkeypatch.setattr(gpu.shutil, "which", lambda executable: f"/bin/{executable}")

    def run(command, **kwargs):
        if command[0].endswith("nvidia-smi"):
            if isinstance(failure, Exception):
                raise failure
            output = failure
        else:
            output = '{"card0": {"Card model": "AMD"}}'
        return subprocess.CompletedProcess(command, 0, stdout=output)

    monkeypatch.setattr(gpu.subprocess, "run", run)
    warnings = []
    devices = gpu.collect_gpus(warnings.append)
    assert len(devices) == 1 and devices[0].vendor == "amd"
    assert len(warnings) == 1 and "nvidia-smi" in warnings[0]


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_gpu_discovery_without_vendor_tools_is_empty(monkeypatch, system):
    monkeypatch.setattr(gpu.platform, "system", lambda: system)
    monkeypatch.setattr(gpu.shutil, "which", lambda executable: None)
    warnings = []
    assert gpu.collect_gpus(warnings.append) == [] and not warnings


@pytest.mark.asyncio
async def test_cancelling_a_command_reaps_its_process_and_clears_service_ownership(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        service={"backend": "http", "token": "test"},
        command=(sys.executable, "-u", "-c", "import os, time; print(os.getpid()); time.sleep(60)"),
    )
    started = asyncio.Event()
    process_ids = []

    async def emit(event):
        process_ids.append(int(event.content.strip()))
        started.set()

    async with app:
        task = asyncio.create_task(run_command(app.context, (), emit))
        try:
            await asyncio.wait_for(started.wait(), 5)
            assert process_ids[0] in app.context.service.cli_processes
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert not app.context.service.cli_processes
        assert not app.context.service.cli_callbacks
        with pytest.raises(ProcessLookupError):
            os.kill(process_ids[0], 0)
