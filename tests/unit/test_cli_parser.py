"""Scheduled commands use the CLI's argument grammar and execution policy."""

import pytest

from axonx.cli.parser import parse_command, validate_cron_command


@pytest.mark.parametrize("argv", [[], ["--token", "token"]])
def test_parser_requires_a_command(argv):
    with pytest.raises(ValueError, match="Missing command"):
        parse_command(argv)


@pytest.mark.parametrize("value", ["3", "true", "null", "01"])
def test_execution_environment_values_remain_strings(value):
    command, _ = parse_command(["exec", "--environment.VALUE", value])
    assert command.arguments == {"environment": {"VALUE": value}}


def test_scheduled_exec_uses_the_cli_argument_contract():
    argv = ("axonx", "exec", "--task", "demo", "--x", "3", "--nested.enabled", "true", "--label", "01")
    validate_cron_command(argv)
    command, _ = parse_command(argv[1:])
    assert command.arguments == {"task": "demo", "x": 3, "nested": {"enabled": True}, "label": "01"}


@pytest.mark.parametrize(
    "argv",
    [
        ("worker", "--task", "demo"),
        ("axonx", "app"),
        ("axonx", "exec"),
        ("axonx", "exec", "--task", "true"),
        ("axonx", "exec", "--task", "demo", "--x"),
        ("axonx", "exec", "--task", "demo", "--task", "other"),
        ("axonx", "exec", "--task", "demo", "--nested", "1", "--nested.enabled", "true"),
        ("axonx", "exec", "--task", "demo", "--target", "remote:1024"),
        ("axonx", "exec", "--task", "demo", "--stream", "false"),
    ],
)
def test_scheduled_exec_rejects_invalid_or_nonlocal_commands(argv):
    with pytest.raises(ValueError):
        validate_cron_command(argv)


@pytest.mark.parametrize("token", ["123", "true", "null", "01", " value "])
def test_credentials_are_preserved_as_text(token):
    command, options = parse_command(["--token", token, "status", "--client-timeout", "3", "--timeout", "5"])
    assert options.token == token
    assert options.timeout == 3
    assert command.arguments == {"timeout": 5}


@pytest.mark.parametrize(
    "arguments",
    [
        ["--task-name", "one", "--task_name", "two"],
        ["--nested", "1", "--nested.enabled", "true"],
        ["--nested.enabled", "true", "--nested", "1"],
        ["--stream-format", "json", "--stream_format", "blocks"],
        ["--stream", "true", "--stream", "false"],
        ["--target"],
        ["--stream", "--task", "demo"],
        ["--value"],
        ["--value", "--unknown"],
        ["--nested..field", "1"],
    ],
)
def test_invalid_or_conflicting_options_are_rejected(arguments):
    with pytest.raises(ValueError):
        parse_command(["exec", *arguments])


def test_target_and_plugin_commands_keep_unparsed_positional_arguments():
    argv = ["plugin", "install", "-e", "./source", "--target", "remote:1024"]
    command, options = parse_command(argv)
    assert options.target == "http://remote:1024"
    assert command.arguments == {}
    assert command.raw_arguments == ("install", "-e", "./source")
    local, _ = parse_command(argv[:-2])
    assert local == command
