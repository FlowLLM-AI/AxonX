"""Exercise CLI routing, remote output and exit status through the public entry point."""

import json
import os

import pytest

from axonx.cli import commands, main, remote
from axonx.client import http as client
from axonx.client.base import RemoteConnectionError, RemoteServiceError
from axonx.client.events import AgentBlockPatch, AgentMessageEvent, ResultEvent
from axonx.client.models import JobResponse
from axonx.task.models.events import LogEvent
from axonx.task.runtime.settings import ExecutionSettings
from axonx.task.storage.workspace import read_entry


@pytest.fixture(autouse=True)
def isolate_cli_environment(monkeypatch):
    monkeypatch.delenv("AXONX_CLI_REQUEST_ID", raising=False)
    monkeypatch.delenv("AXONX_TARGET_TOKEN", raising=False)
    monkeypatch.delenv("AXONX_SERVICE_TOKEN", raising=False)
    monkeypatch.setattr(remote, "load_env", lambda **kwargs: {})
    monkeypatch.setattr(commands, "load_env", lambda **kwargs: {})


@pytest.mark.parametrize("argv", [[], ["--help"], ["-h"], ["plugin", "--help"]])
def test_help_is_offline_and_returns_success(argv, capsys):
    assert main(argv) == 0
    assert "usage:" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("success", [True, False])
@pytest.mark.parametrize("details", [[], ["--detail", "full"]])
@pytest.mark.parametrize("target", [False, True])
def test_job_defaults_explicit_options_and_response_status(monkeypatch, capsys, success, details, target):
    calls = []

    async def run_job(name, arguments, **connection):
        calls.append((name, arguments, connection))
        return JobResponse(answer={"label": "中文"}, success=success)

    monkeypatch.setattr(client, "run_remote_job", run_job)
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "service-token")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "target-token")
    connection_options = ["--target", "remote:1024"] if target else []
    assert main(["status", *details, "--client-timeout", "4", *connection_options]) == (0 if success else 1)
    assert calls == [
        (
            "status",
            {"detail": "full" if details else "summary"},
            {
                "target": "http://remote:1024" if target else None,
                "timeout": 4.0,
                "token": "target-token" if target else "service-token",
            },
        )
    ]
    assert json.loads(capsys.readouterr().out)["success"] is success


@pytest.mark.parametrize(
    ("argv", "arguments"),
    [
        (["list_task_defs", "--include-schemas", "false"], {"include_schemas": False}),
        (["get_task_def", "--task", "demo"], {"task": "demo"}),
    ],
)
def test_task_definitions_use_service_jobs(monkeypatch, capsys, argv, arguments):
    async def run_job(name, inputs, **connection):
        assert name == argv[0]
        assert inputs == arguments
        assert connection["target"] is None
        return JobResponse(answer={"source": "service"})

    monkeypatch.setattr(client, "run_remote_job", run_job)
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["answer"] == {"source": "service"}


@pytest.mark.parametrize("stream_format", ["json", "blocks"])
def test_streams_preserve_agent_patches_and_terminal_response(monkeypatch, capsys, stream_format):
    events = [
        AgentMessageEvent(
            session_id="session",
            type_name="assistant",
            message_uuid="message",
            role="assistant",
            sequence=0,
            presentation=[AgentBlockPatch(operation="append", block_id="text", block_type="text", delta="中文")],
        ),
        ResultEvent(answer="done", success=True, metadata={"complete": True}),
    ]

    async def stream_job(name, arguments, **connection):
        assert name == "agent_chat"
        assert connection["token"] == "123"
        for event in events:
            yield event

    monkeypatch.setattr(client, "stream_remote_job", stream_job)
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "ignored")
    assert main(["agent_chat", "--token", "123", "--stream", "true", "--stream-format", stream_format]) == 0
    output = capsys.readouterr().out
    if stream_format == "json":
        assert [json.loads(line) for line in output.splitlines()] == [event.model_dump(mode="json") for event in events]
    else:
        assert "===== BLOCK: Agent / text / append =====" in output
        assert '"delta": "中文"' in output
        assert "===== BLOCK: ResultEvent =====" in output
        assert '"complete": true' in output


@pytest.mark.parametrize(
    ("argv", "forwarded"),
    [
        (["exec", "--task", "demo"], ["exec", "--task", "demo", "--client-timeout", "4.0"]),
        (["plugin", "install", "-e", "./source"], ["plugin", "install", "-e", "./source"]),
        (
            ["kill", "--task-id", "base#demo#check", "--workspace-dir", "/data"],
            ["kill", "--task-id", "base#demo#check", "--workspace-dir", "/data", "--client-timeout", "4.0"],
        ),
    ],
)
def test_target_forwards_raw_cli_arguments_without_credentials(monkeypatch, argv, forwarded):
    calls = []

    async def stream_job(name, arguments, **connection):
        calls.append((name, arguments, connection))
        yield ResultEvent(answer={"exit_code": 0}, success=True)

    monkeypatch.setattr(client, "stream_remote_job", stream_job)
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "target-token")
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "service-token")
    assert main([*argv, "--target", "remote:1024", "--client-timeout", "4"]) == 0
    assert calls == [
        ("cli", {"argv": forwarded}, {"target": "http://remote:1024", "timeout": 4.0, "token": "target-token"})
    ]


@pytest.mark.parametrize(("code", "expected"), [(0, 0), (7, 7), (-15, 143), ("0", 1), (True, 1), (None, 1)])
def test_target_preserves_output_channels_exit_status_and_closes_stream(monkeypatch, capsys, code, expected):
    closed = []

    async def stream_job(*args, **kwargs):
        try:
            yield LogEvent(channel="stdout", content="out\n")
            yield LogEvent(channel="stderr", content="err\n")
            yield ResultEvent(answer={"exit_code": code}, success=code == 0)
        finally:
            closed.append(True)

    monkeypatch.setattr(client, "stream_remote_job", stream_job)
    assert main(["exec", "--task", "demo", "--target", "remote:1024"]) == expected
    captured = capsys.readouterr()
    assert captured.out == "out\n"
    assert captured.err.startswith("err\n")
    assert closed == [True]


@pytest.mark.parametrize("target", [False, True])
def test_missing_terminal_result_returns_failure(monkeypatch, target):
    async def stream_job(*args, **kwargs):
        yield LogEvent(channel="stdout", content="")

    monkeypatch.setattr(client, "stream_remote_job", stream_job)
    options = ["--target", "remote:1024"] if target else []
    assert main(["status", "--stream", "true", *options]) == 1


@pytest.mark.parametrize("argv", [["app"], ["cli"], ["exec", "--target", "remote:1024"]])
def test_forwarded_cli_cannot_start_or_forward_recursively(monkeypatch, capsys, argv):
    monkeypatch.setenv("AXONX_CLI_REQUEST_ID", "request")
    assert main(argv) == 2
    assert "Remote CLI cannot" in capsys.readouterr().err


def test_plugin_usage_errors_return_a_code_instead_of_exiting(capsys):
    assert main(["plugin", "install"]) == 2
    assert "required" in capsys.readouterr().err
    assert main(["plugin", "install", "-e", ".", "--output", "dist"]) == 2
    assert "--editable cannot be combined with --output" in capsys.readouterr().err


@pytest.mark.parametrize("explicit", [False, True])
def test_plugin_build_uses_the_selected_workspace_without_a_service(tmp_path, monkeypatch, capsys, explicit):
    from axonx.plugin import installer

    selected = tmp_path / ("explicit" if explicit else "environment")
    monkeypatch.setenv("AXONX_WORKSPACE_DIR", str(tmp_path / "environment"))
    calls = []

    def prepare(source, *, cache_dir, output):
        calls.append((source, cache_dir, output))
        return {"wheel": "example.whl"}

    monkeypatch.setattr(installer, "prepare_artifact", prepare)
    monkeypatch.setattr(client, "run_remote_job", lambda *a, **k: pytest.fail("Build must work offline"))
    argv = ["plugin", "build", "."]
    if explicit:
        argv.extend(["--workspace-dir", str(selected)])
    assert main(argv) == 0
    assert calls == [(".", selected / "tmp/plugins", None)]
    assert "example.whl" in capsys.readouterr().out


@pytest.mark.parametrize("override", [False, True])
def test_exec_and_kill_share_service_configuration_and_cli_overrides(tmp_path, monkeypatch, capsys, override):
    service_workspace = tmp_path / "service"
    selected_workspace = tmp_path / "override" if override else service_workspace
    settings = ExecutionSettings(
        workspace_dir=str(service_workspace),
        log_dir=str(tmp_path / "logs"),
        log_to_console=False,
        log_to_file=False,
        execution_target="worker:1024",
        environment={"AXONX_TEST_CONFIG_VALUE": "service", "AXONX_TEST_CONFIG_ONLY": "service"},
    ).model_dump()
    for key in settings["environment"]:
        monkeypatch.setenv(key, "before")
    calls = []

    async def get_config(name, arguments, **connection):
        assert name == "get_config"
        assert arguments == {}
        calls.append(connection)
        return JobResponse(answer=settings)

    monkeypatch.setattr(client, "run_remote_job", get_config)
    runtime = ["--environment.AXONX_TEST_CONFIG_VALUE", "cli"]
    if override:
        runtime.extend(["--workspace-dir", str(selected_workspace), "--execution-target", "null", "--timezone", "UTC"])
    connection = ["--token", "explicit-token", "--client-timeout", "2"]
    assert main(["exec", "--task", "demo", "--task-name", "config", "--x", "2", "--y", "3", *runtime, *connection]) == 0
    metadata = read_entry(selected_workspace, "base#demo#config")
    assert metadata.output_params["result"] == 5
    assert metadata.execution_target == (None if override else "http://worker:1024")
    assert os.environ["AXONX_TEST_CONFIG_VALUE"] == "cli"
    assert os.environ["AXONX_TEST_CONFIG_ONLY"] == "service"
    assert "workspace_dir" not in metadata.input_params
    assert main(["kill", "--task-id", metadata.task_id, *runtime, *connection]) == 0
    assert calls == [{"target": None, "timeout": 2.0, "token": "explicit-token"}] * 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["task_id"] == metadata.task_id


def test_exec_falls_back_only_when_service_connection_fails(tmp_path, monkeypatch, capsys):
    async def unavailable(*args, **kwargs):
        raise RemoteConnectionError("unreachable")

    monkeypatch.setattr(client, "run_remote_job", unavailable)
    assert (
        main(
            [
                "exec",
                "--task",
                "demo",
                "--task-name",
                "offline",
                "--x",
                "2",
                "--y",
                "3",
                "--workspace-dir",
                str(tmp_path),
                "--log-dir",
                str(tmp_path / "logs"),
                "--log-to-console",
                "false",
                "--log-to-file",
                "false",
            ]
        )
        == 0
    )
    assert read_entry(tmp_path, "base#demo#offline").output_params["result"] == 5
    assert "built-in defaults" in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["auth", "business", "invalid", "incomplete"])
def test_exec_does_not_fall_back_on_rejected_or_invalid_configuration(tmp_path, monkeypatch, failure):
    async def get_config(*args, **kwargs):
        if failure == "auth":
            raise RemoteServiceError("rejected", status_code=401)
        return JobResponse(answer=[] if failure == "invalid" else {}, success=failure != "business")

    monkeypatch.setattr(client, "run_remote_job", get_config)
    assert main(["exec", "--task", "demo", "--workspace-dir", str(tmp_path)]) == 1
    assert not list(tmp_path.iterdir())
