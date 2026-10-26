"""Scheduled commands use the CLI's argument grammar and execution policy."""

import pytest

from axonx.cli.parser import parse_command, validate_cron_command


def test_scheduled_exec_uses_the_cli_argument_contract():
    argv = ("axonx", "exec", "--task", "demo", "--x", "3", "--nested.enabled", "true", "--label", "01")
    validate_cron_command(argv)
    command, _ = parse_command(argv[1:])
    assert command.arguments == {"task": "demo", "x": 3, "nested": {"enabled": True}, "label": "01"}


@pytest.mark.parametrize(
    "argv",
    [
        ("worker", "--task", "demo"),
        ("axonx", "start"),
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
