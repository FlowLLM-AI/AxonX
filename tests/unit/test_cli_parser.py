"""CLI connection options must route to the client, not to Jobs."""

import pytest

from axonx.app.components.job import JobResponse
from axonx.cli.main import _load_client_options, _run_plugin, _run_remote_job
from axonx.cli.options import ClientOptions
from axonx.cli.parser import parse_command


def test_wait_task_accepts_client_timeout():
    """Keep client timeout outside wait-task arguments."""
    command, client = parse_command(
        [
            "wait_task",
            "--task-id",
            "etl#qlib_a158_etl#demo",
            "--run-id",
            "run-001",
            "--client-timeout",
            "86400",
        ],
    )
    assert client.timeout == 86400
    assert command.arguments["task_id"] == "etl#qlib_a158_etl#demo"
    assert "timeout" not in command.arguments


def test_remote_job_accepts_trailing_connection_options():
    """Route trailing connection options to the remote client."""
    command, client = parse_command(
        [
            "status",
            "--task-id",
            "etl#qlib_a158_etl#demo",
            "--target",
            "192.0.2.10:1024",
            "--token",
            "secret",
        ],
    )
    assert (client.target, client.token) == ("http://192.0.2.10:1024", "secret")
    assert list(command.raw_arguments) == ["--task-id", "etl#qlib_a158_etl#demo"]


def test_plugin_accepts_trailing_connection_options():
    """Separate plugin arguments from connection options."""
    command, client = parse_command(
        ["plugin", "install", "plugins/qlib_a158", "--target", "192.0.2.10:1024"],
    )
    assert list(command.raw_arguments) == ["install", "plugins/qlib_a158"]
    assert client.target == "http://192.0.2.10:1024"


def test_python_timeout_remains_job_parameter():
    """Preserve multiline Python source and its execution timeout."""
    code = "from pathlib import Path\nprint(Path.cwd())"
    command, client = parse_command(["python", "--code", code, "--timeout", "30"])
    assert command.arguments["code"] == code
    assert command.arguments["timeout"] == 30
    assert client.timeout == 60


def test_client_timeout_is_separate_from_job_timeout():
    """Allow independent transport and execution timeouts."""
    command, client = parse_command(
        ["python", "--code", "print(1)", "--timeout", "30", "--client-timeout", "180"],
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


def test_target_preserves_local_command_arguments():
    command, options = parse_command(["exec", "--task", "demo", "--target", "node-b:1024"])
    assert command.arguments == {}
    assert command.raw_arguments == ("--task", "demo")
    assert options.target == "http://node-b:1024"


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

    monkeypatch.setattr("axonx.app.components.client.remote.run_remote_job", run_remote_job)
    command, client = parse_command(
        ["status", *(["--target", target] if target else [])],
    )
    assert _run_remote_job(command, client) == 0
    assert received["token"] == expected_token


def test_plugin_cli_receives_only_local_arguments(monkeypatch):
    received = []
    monkeypatch.setattr("axonx.cli.plugin.plugin_cli", lambda argv: received.append(argv) or 0)
    command, _ = parse_command(["plugin", "list"])
    assert _run_plugin(command) == 0
    assert received == [("list",)]


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


@pytest.mark.parametrize(
    ("action", "defaults"),
    [
        ("status", {"detail": "summary"}),
        ("wait_task", {"detail": "summary"}),
        ("preview_file", {"limit": 20, "max_bytes": 8192}),
        ("list_installed_task_definitions", {"include_schemas": False}),
        ("list_agent_sessions", {"limit": 20}),
        ("get_agent_session", {"limit": 20}),
    ],
)
@pytest.mark.parametrize("explicit", [False, True])
def test_cli_query_defaults_are_lightweight_and_overridable(monkeypatch, action, defaults, explicit):
    received = {}

    async def run_remote_job(_name, arguments, **_options):
        received.update(arguments)
        return JobResponse()

    monkeypatch.setattr("axonx.app.components.client.remote.run_remote_job", run_remote_job)
    options = {"detail": "full"} if "detail" in defaults else {"limit": 100}
    if action == "preview_file":
        options["max_bytes"] = 65536
    if action == "list_installed_task_definitions":
        options = {"include_schemas": True}
    argv = [action]
    if explicit:
        for name, value in options.items():
            argv.extend(["--" + name.replace("_", "-"), str(value)])
    command, client = parse_command(argv)
    assert _run_remote_job(command, client) == 0
    assert received == (options if explicit else defaults)
