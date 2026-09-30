"""CLI connection options must route to the client, not to Jobs."""

import importlib

import pytest

from axonx.cli.main import _run_plugin, _run_remote_job
from axonx.cli.parser import parse_command
from axonx.components.client import ClientOptions
from axonx.components.job import JobResponse


def test_wait_task_accepts_trailing_client_timeout():
    command, client = parse_command(
        [
            "wait_task",
            "--task-id",
            "etl#a158_etl#demo",
            "--run-id",
            "run-001",
            "--timeout",
            "86400",
        ]
    )
    assert client.timeout == 86400
    assert command.arguments["task_id"] == "etl#a158_etl#demo"
    assert "timeout" not in command.arguments


def test_remote_job_accepts_trailing_connection_options():
    command, client = parse_command(
        [
            "status",
            "--task-id",
            "etl#a158_etl#demo",
            "--target",
            "192.0.2.10:1024",
            "--token",
            "secret",
        ]
    )
    assert (client.target, client.token) == ("http://192.0.2.10:1024", "secret")
    assert "target" not in command.arguments


def test_plugin_accepts_trailing_connection_options():
    command, client = parse_command(
        ["plugin", "install", "plugins/a158", "--target", "192.0.2.10:1024"]
    )
    assert command.arguments["_axonx_argv"] == ["install", "plugins/a158"]
    assert client.target == "http://192.0.2.10:1024"


def test_shell_timeout_remains_job_parameter():
    command, client = parse_command(["shell", "--command", "pwd", "--timeout", "30"])
    assert command.arguments["timeout"] == 30
    assert client.timeout == 60


def test_client_timeout_is_separate_from_job_timeout():
    command, client = parse_command(
        ["shell", "--command", "pwd", "--timeout", "30", "--client-timeout", "180"]
    )
    assert command.arguments["timeout"] == 30
    assert client.timeout == 180


def test_custom_job_timeout_remains_business_argument():
    command, client = parse_command(
        ["custom_job", "--timeout", "5", "--client-timeout", "30"]
    )
    assert command.arguments["timeout"] == 5
    assert client.timeout == 30


def test_legacy_leading_address_options_still_work():
    command, client = parse_command(
        ["--host-ip", "192.0.2.10", "--host-port", "1024", "status"]
    )
    assert command.action == "status"
    assert client.target == "http://192.0.2.10:1024"


def test_legacy_trailing_address_options_still_work():
    command, client = parse_command(
        ["status", "--host-ip", "192.0.2.10", "--host-port", "1024"]
    )
    assert command.arguments == {"_axonx_argv": []}
    assert client.target == "http://192.0.2.10:1024"


def test_agent_client_timeout_is_not_sent_as_job_argument():
    command, client = parse_command(["agent_chat", "--message", "hi", "--timeout", "180"])
    assert "timeout" not in command.arguments
    assert client.timeout == 180


def test_rejects_repeated_client_option():
    with pytest.raises(ValueError, match="Duplicate client option"):
        parse_command(
            ["status", "--target", "127.0.0.1:1024", "--target", "192.0.2.10:1024"]
        )


def test_rejects_target_for_local_command():
    with pytest.raises(ValueError, match="local command"):
        parse_command(["start", "--target", "127.0.0.1:1024"])


@pytest.mark.parametrize(
    ("target", "expected_token"),
    [(None, "local-secret"), ("192.0.2.10:1024", None)],
)
def test_job_only_defaults_to_local_token_without_target(
    monkeypatch, target, expected_token
):
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "local-secret")
    received = {}

    async def run_remote_job(_name, _arguments, **options):
        received.update(options)
        return JobResponse()

    cli_main = importlib.import_module("axonx.cli.main")
    monkeypatch.setattr(cli_main, "run_remote_job", run_remote_job)
    command, client = parse_command(
        ["status", *(["--target", target] if target else [])]
    )
    assert _run_remote_job(command, client) == 0
    assert received["token"] == expected_token


@pytest.mark.parametrize(
    ("target", "expected_token"),
    [(None, "local-secret"), ("192.0.2.10:1024", None)],
)
def test_plugin_only_defaults_to_local_token_without_target(
    monkeypatch, target, expected_token
):
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "local-secret")
    received = {}

    def plugin_cli(_argv, options):
        received["token"] = options.token
        return 0

    monkeypatch.setattr("axonx.plugin_kit.cli.plugin_cli", plugin_cli)
    command, _ = parse_command(["plugin", "list"])
    assert _run_plugin(command, ClientOptions(target=target)) == 0
    assert received["token"] == expected_token
