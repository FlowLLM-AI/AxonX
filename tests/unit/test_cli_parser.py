"""CLI connection options must route to the client, not to Jobs."""

import importlib

import pytest

from axonx.cli.main import _load_client_options, _run_plugin, _run_remote_job
from axonx.cli.parser import parse_command
from axonx.components.client import ClientOptions
from axonx.components.job import JobResponse


def test_wait_task_accepts_client_timeout():
    """Keep client timeout outside wait-task arguments."""
    command, client = parse_command(
        [
            "wait_task",
            "--task-id",
            "etl#a158_etl#demo",
            "--run-id",
            "run-001",
            "--client-timeout",
            "86400",
        ],
    )
    assert client.timeout == 86400
    assert command.arguments["task_id"] == "etl#a158_etl#demo"
    assert "timeout" not in command.arguments


def test_remote_job_accepts_trailing_connection_options():
    """Route trailing connection options to the remote client."""
    command, client = parse_command(
        [
            "status",
            "--task-id",
            "etl#a158_etl#demo",
            "--target",
            "192.0.2.10:1024",
            "--token",
            "secret",
        ],
    )
    assert (client.target, client.token) == ("http://192.0.2.10:1024", "secret")
    assert "target" not in command.arguments


def test_plugin_accepts_trailing_connection_options():
    """Separate plugin arguments from connection options."""
    command, client = parse_command(
        ["plugin", "install", "plugins/a158", "--target", "192.0.2.10:1024"],
    )
    assert command.arguments["_axonx_argv"] == ["install", "plugins/a158"]
    assert client.target == "http://192.0.2.10:1024"


def test_shell_timeout_remains_job_parameter():
    """Keep shell execution timeout as a business argument."""
    command, client = parse_command(["shell", "--command", "pwd", "--timeout", "30"])
    assert command.arguments["timeout"] == 30
    assert client.timeout == 60


def test_client_timeout_is_separate_from_job_timeout():
    """Allow independent transport and execution timeouts."""
    command, client = parse_command(
        ["shell", "--command", "pwd", "--timeout", "30", "--client-timeout", "180"],
    )
    assert command.arguments["timeout"] == 30
    assert client.timeout == 180


def test_custom_job_timeout_remains_business_argument():
    """Preserve custom Job timeout arguments."""
    command, client = parse_command(
        ["custom_job", "--timeout", "5", "--client-timeout", "30"],
    )
    assert command.arguments["timeout"] == 5
    assert client.timeout == 30


def test_agent_client_timeout_is_not_sent_as_job_argument():
    """Keep client timeout out of Agent arguments."""
    command, client = parse_command(
        ["agent_chat", "--message", "hi", "--client-timeout", "180"],
    )
    assert "timeout" not in command.arguments
    assert client.timeout == 180


def test_rejects_repeated_client_option():
    """Reject ambiguous repeated connection options."""
    with pytest.raises(ValueError, match="Duplicate client option"):
        parse_command(
            ["status", "--target", "127.0.0.1:1024", "--target", "192.0.2.10:1024"],
        )


def test_rejects_target_for_local_command():
    """Reject remote targets for local-only commands."""
    with pytest.raises(ValueError, match="local command"):
        parse_command(["start", "--target", "127.0.0.1:1024"])


@pytest.mark.parametrize(
    ("target", "expected_token"),
    [(None, "local-secret"), ("192.0.2.10:1024", "remote-secret")],
)
def test_job_defaults_to_token_for_target(monkeypatch, target, expected_token):
    """Choose the environment token for the Job destination."""
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "local-secret")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "remote-secret")
    received = {}

    async def run_remote_job(_name, _arguments, **options):
        received.update(options)
        return JobResponse()

    cli_main = importlib.import_module("axonx.cli.main")
    monkeypatch.setattr(cli_main, "run_remote_job", run_remote_job)
    command, client = parse_command(
        ["status", *(["--target", target] if target else [])],
    )
    assert _run_remote_job(command, client) == 0
    assert received["token"] == expected_token


@pytest.mark.parametrize(
    ("target", "expected_token"),
    [(None, "local-secret"), ("192.0.2.10:1024", "remote-secret")],
)
def test_plugin_defaults_to_token_for_target(monkeypatch, target, expected_token):
    """Choose the environment token for the plugin destination."""
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "local-secret")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "remote-secret")
    received = {}

    def plugin_cli(_argv, options):
        received["token"] = options.token
        return 0

    monkeypatch.setattr("axonx.plugin_kit.cli.plugin_cli", plugin_cli)
    command, _ = parse_command(["plugin", "list"])
    assert _run_plugin(command, ClientOptions(target=target)) == 0
    assert received["token"] == expected_token


@pytest.mark.parametrize("target", [None, "192.0.2.10:1024"])
@pytest.mark.parametrize("explicit_token", [None, "explicit-secret"])
def test_cli_loads_token_from_env_file(monkeypatch, tmp_path, target, explicit_token):
    """Load dotenv defaults while preserving explicit tokens."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AXONX_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("AXONX_TARGET_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "AXONX_SERVICE_TOKEN=local-secret\nAXONX_TARGET_TOKEN=remote-secret\n",
    )
    options = _load_client_options(
        ClientOptions(target=target, token=explicit_token),
    )
    assert options.token == (explicit_token or ("remote-secret" if target else "local-secret"))


def test_remote_token_does_not_fall_back_to_local_token(monkeypatch, tmp_path):
    """Avoid sending the local service token to remote targets."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "local-secret")
    monkeypatch.delenv("AXONX_TARGET_TOKEN", raising=False)
    (tmp_path / ".env").write_text("")
    options = _load_client_options(ClientOptions(target="192.0.2.10:1024"))
    assert options.token is None
