"""Exercise deployment port cleanup without running installs or stopping real processes."""

# Execute the actual embedded Python so regression tests cover the shipped script.
# pylint: disable=exec-used

from pathlib import Path
import os
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/deploy.sh"
CLEANUP = SCRIPT.read_text(encoding="utf-8").split("python - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


@pytest.fixture
def cleanup(monkeypatch):
    namespace = {}
    exec(compile(CLEANUP.split("\npids = listening_pids()", 1)[0], str(SCRIPT), "exec"), namespace)
    monkeypatch.setattr(namespace["sys"], "platform", "darwin")
    monkeypatch.setattr(namespace["os"], "kill", Mock())
    monkeypatch.setattr(namespace["psutil"], "net_connections", Mock(side_effect=AssertionError("global scan")))
    return namespace


def test_macos_finds_only_listener_pids(cleanup, monkeypatch):
    current_pid = cleanup["os"].getpid()
    query = Mock(return_value=SimpleNamespace(returncode=0, stdout=f"12345\n12345\n{current_pid}\n", stderr=""))
    monkeypatch.setattr(cleanup["subprocess"], "run", query)
    assert cleanup["listening_pids"]() == {12345}
    assert query.call_args.args[0] == ["lsof", "-nP", "-iTCP:1024", "-sTCP:LISTEN", "-t"]


def test_empty_port_does_not_kill_processes(cleanup, monkeypatch, capsys):
    monkeypatch.setattr(
        cleanup["subprocess"], "run", Mock(return_value=SimpleNamespace(returncode=1, stdout="", stderr=""))
    )
    with pytest.raises(SystemExit) as error:
        exec(compile(CLEANUP, str(SCRIPT), "exec"), cleanup)
    assert error.value.code == 0
    assert "权限范围内未发现" in capsys.readouterr().out
    cleanup["os"].kill.assert_not_called()


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(returncode=1, stdout="", stderr="Permission denied"),
        SimpleNamespace(returncode=2, stdout="", stderr=""),
        SimpleNamespace(returncode=1, stdout="12345\n", stderr=""),
    ],
)
def test_query_failure_aborts_with_manual_instructions(cleanup, monkeypatch, result):
    monkeypatch.setattr(cleanup["subprocess"], "run", Mock(return_value=result))
    with pytest.raises(SystemExit, match="sudo lsof -nP -iTCP:1024 -sTCP:LISTEN"):
        exec(compile(CLEANUP, str(SCRIPT), "exec"), cleanup)
    cleanup["os"].kill.assert_not_called()


@pytest.mark.parametrize(
    ("exception", "message"),
    [(FileNotFoundError(), "未找到 lsof"), (subprocess.TimeoutExpired("lsof", 10), "查询 1024 端口失败")],
)
def test_query_execution_errors_are_readable(cleanup, monkeypatch, exception, message):
    monkeypatch.setattr(cleanup["subprocess"], "run", Mock(side_effect=exception))
    with pytest.raises(SystemExit, match=message):
        cleanup["listening_pids"]()


@pytest.mark.parametrize("output", ["invalid\n", "0\n", "-1\n"])
def test_invalid_pids_cannot_reach_kill(cleanup, monkeypatch, output):
    monkeypatch.setattr(
        cleanup["subprocess"], "run", Mock(return_value=SimpleNamespace(returncode=0, stdout=output, stderr=""))
    )
    with pytest.raises(SystemExit, match="无法安全清理"):
        exec(compile(CLEANUP, str(SCRIPT), "exec"), cleanup)
    cleanup["os"].kill.assert_not_called()


def test_kill_permission_error_identifies_listener(cleanup, capsys):
    cleanup["os"].kill.side_effect = PermissionError()
    assert cleanup["stop_process"](12345, signal.SIGTERM) is False
    warning = capsys.readouterr().err
    assert "无权停止监听 1024 端口的进程 PID=12345" in warning
    assert "sudo kill -TERM <PID>" in warning


def test_permission_denied_does_not_block_startup(cleanup, monkeypatch, capsys):
    cleanup["os"].kill.side_effect = PermissionError()
    monkeypatch.setattr(
        cleanup["subprocess"], "run", Mock(return_value=SimpleNamespace(returncode=0, stdout="12345\n", stderr=""))
    )
    exec(compile(CLEANUP, str(SCRIPT), "exec"), cleanup)
    cleanup["os"].kill.assert_called_once_with(12345, signal.SIGTERM)
    output = capsys.readouterr()
    assert "继续执行 axonx start" in output.out
    assert "端口 1024 已释放" not in output.out


def test_process_already_exited_is_harmless(cleanup):
    cleanup["os"].kill.side_effect = ProcessLookupError()
    cleanup["stop_process"](12345, signal.SIGTERM)


def test_linux_access_denied_has_recovery_instructions(cleanup, monkeypatch):
    monkeypatch.setattr(cleanup["sys"], "platform", "linux")
    monkeypatch.setattr(cleanup["psutil"], "net_connections", Mock(side_effect=psutil.AccessDenied(48391)))
    with pytest.raises(SystemExit, match="当前用户无权查询系统 TCP 连接") as error:
        cleanup["listening_pids"]()
    assert "sudo lsof" in str(error.value)


def test_cleanup_waits_for_listener_to_exit(cleanup, monkeypatch, capsys):
    monkeypatch.setattr(
        cleanup["subprocess"],
        "run",
        Mock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout="12345\n", stderr=""),
                SimpleNamespace(returncode=1, stdout="", stderr=""),
                SimpleNamespace(returncode=1, stdout="", stderr=""),
            ]
        ),
    )
    exec(compile(CLEANUP, str(SCRIPT), "exec"), cleanup)
    cleanup["os"].kill.assert_called_once_with(12345, signal.SIGTERM)
    assert "端口 1024 已释放" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [[], ["--config", "remote"], ["--config", "configs/remote machine.yaml"]])
def test_start_receives_script_arguments(tmp_path, arguments):
    axonx = tmp_path / "axonx"
    axonx.write_text('#!/bin/sh\nprintf "<%s>\\n" "$@"\n', encoding="utf-8")
    axonx.chmod(0o755)
    start = SCRIPT.read_text(encoding="utf-8").splitlines()[-1]
    result = subprocess.run(
        ["bash", "-c", start, "deploy.sh", *arguments],
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [f"<{argument}>" for argument in ["start", *arguments]]
