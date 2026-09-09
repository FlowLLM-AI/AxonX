"""Command-line parsing and execution tests."""

# Tests favor descriptive class and function names over repeated docstrings.
# pylint: disable=missing-class-docstring,missing-function-docstring

import json

import pytest
from pydantic import ValidationError

from axonx import cli
from axonx.components.client import HttpClient
from axonx.schema import Command, HttpClientOptions, Response
from axonx.task import BaseConfig, BaseTask
from axonx.utils.cli_utils import CommandParser


class CliConfig(BaseConfig):
    amount: int
    dry_run: bool = False


class CliTask(BaseTask):
    config: CliConfig
    output_keys = ("amount", "dry_run")

    def build_task_steps(self):
        yield self.record_config

    def record_config(self):
        self.context.update(amount=self.config.amount, dry_run=self.config.dry_run)


def test_local_task_uses_registered_config(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_installed_tasks", lambda: {"sample": CliTask})

    assert cli.main(["exec", "--task", "sample", "--amount", "3", "--dry-run", "true"]) == 0

    assert json.loads(capsys.readouterr().out) == {"amount": 3, "dry_run": True}


def test_submit_forwards_the_same_task_arguments(monkeypatch, capsys):
    calls = []

    class Client:
        def __init__(self, **options):
            calls.append(("client", options))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def run_job(self, name, **arguments):
            calls.append((name, arguments))
            return Response(answer={"run_id": "run-1"})

    monkeypatch.setattr(cli, "HttpClient", Client)

    status = cli.main(
        [
            "--url",
            "http://service:9000",
            "--timeout",
            "5",
            "submit",
            "--task",
            "sample",
            "--amount",
            "3",
            "--dry-run",
            "true",
        ],
    )

    assert status == 0
    assert calls == [
        ("client", {"url": "http://service:9000", "timeout": 5}),
        ("submit", {"task": "sample", "amount": 3, "dry_run": True}),
    ]
    assert json.loads(capsys.readouterr().out)["answer"] == {"run_id": "run-1"}


def test_exec_without_arguments_lists_available_tasks(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_installed_tasks", lambda: {"sample": CliTask})

    assert cli.main(["exec"]) == 0

    assert capsys.readouterr().out == f"sample\t{__name__}.CliTask\n"


def test_exec_does_not_discover_unconfigured_plugin(capsys):
    assert cli.main(["exec", "--task", "sales"]) == 2
    assert "Unknown Task" in capsys.readouterr().err


def test_task_options_are_strict(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_installed_tasks", lambda: {"sample": CliTask})

    assert cli.main(["exec", "--task", "sample", "--amount"]) == 2
    assert "pairs like --field value" in capsys.readouterr().err


def test_command_options_support_nested_fields():
    command = CommandParser(
        [
            "deploy",
            "--service.port",
            "2333",
            "--service.public-host",
            "example.test",
        ],
    ).parse()

    assert command.arguments == {
        "service": {"port": 2333, "public_host": "example.test"},
    }


def test_nested_options_reject_scalar_conflicts(capsys):
    assert cli.main(["start", "--service", "null", "--service.port", "2333"]) == 2
    assert "already a value" in capsys.readouterr().err


def test_command_uses_validated_http_client_options():
    command = CommandParser(
        [
            "--url",
            "https://service.internal/",
            "--timeout",
            "5",
            "status",
        ],
    ).parse()

    assert isinstance(command, Command)
    assert isinstance(command.client, HttpClientOptions)
    assert command.client.url == "https://service.internal"
    assert command.client.timeout == 5

    with pytest.raises(ValidationError):
        HttpClientOptions(timeout=True)
    with pytest.raises(ValidationError):
        HttpClient(url="service.internal")


def test_client_option_names_are_still_valid_actions():
    command = CommandParser(["timeout"]).parse()

    assert command.action == "timeout"
