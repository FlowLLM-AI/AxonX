"""Check shared configuration semantics and log retention protections."""

import fcntl
import os
from time import time

import pytest

from axonx.app.config.loader import ConfigLoader
from axonx.cli.parser import parse_command
from axonx.utils.env import expand_env_vars, find_env_file, load_env
from axonx.utils.logging import (
    LOG_ARGUMENT_MAX_LENGTH,
    LOG_RETENTION_SECONDS,
    LoggingConfig,
    cleanup_log_files,
    configure_logging,
    format_log_arguments,
    get_log_path,
    get_logger,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("FALSE", False),
        ("null", None),
        ("None", None),
        ("42", 42),
        ("2.5", 2.5),
        ("1e3", 1000.0),
        ("000123", "000123"),
        ("-01", "-01"),
        ('[1, "2"]', [1, "2"]),
        ('{"enabled": true}', {"enabled": True}),
        ("  hello  ", "hello"),
    ],
)
def test_cli_and_file_config_share_value_conversion(tmp_path, monkeypatch, raw, expected):
    monkeypatch.setenv("AXONX_TEST_VALUE", raw)
    path = tmp_path / "values.yaml"
    path.write_text('value: ${AXONX_TEST_VALUE}\nliteral: "true"\n')
    config = ConfigLoader(tmp_path).load(path)
    command, _ = parse_command(("exec", "--value", raw))
    assert config == {"value": expected, "literal": "true"}
    assert command.arguments == {"value": expected}
    assert type(config["value"]) is type(expected)
    assert type(command.arguments["value"]) is type(expected)


def test_env_discovery_and_loading_preserve_process_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    path = tmp_path / ".env"
    path.write_text("# comment\nAXONX_TEST_PRESENT=file\nAXONX_TEST_NEW='new=value'\n")
    nested = tmp_path / "one/two"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.setenv("AXONX_TEST_PRESENT", "process")
    monkeypatch.delenv("AXONX_TEST_NEW", raising=False)

    assert find_env_file(search_depth=1) is None
    assert find_env_file(search_depth=2) == path
    assert load_env() == {"AXONX_TEST_PRESENT": "process", "AXONX_TEST_NEW": "new=value"}
    assert os.environ["AXONX_TEST_PRESENT"] == "process"
    assert os.environ["AXONX_TEST_NEW"] == "new=value"
    assert load_env(path, override=True)["AXONX_TEST_PRESENT"] == "file"


def test_env_expansion_handles_nested_defaults_without_mutating_input(monkeypatch):
    monkeypatch.setenv("AXONX_TEST_PRESENT", "process")
    source = {
        "nested": ["${AXONX_TEST_PRESENT}", "${MISSING:-false}", "${EMPTY:-fallback}"],
        "path": "/data/${NAME:-default}",
        "literal": "01",
        "number": 7,
    }
    assert expand_env_vars(source, {"AXONX_TEST_PRESENT": "explicit", "EMPTY": ""}) == {
        "nested": ["explicit", False, ""],
        "path": "/data/default",
        "literal": "01",
        "number": 7,
    }
    assert source["nested"][0] == "${AXONX_TEST_PRESENT}"
    assert os.environ["AXONX_TEST_PRESENT"] == "process"
    with pytest.raises(ValueError, match="MISSING"):
        expand_env_vars("${MISSING}", {})


def test_log_cleanup_protects_active_locked_recent_and_unowned_files(tmp_path):
    prefix = f"2000-01-01_00-00-00_{os.getpid()}"
    identity = "a" * 64
    active = tmp_path / f"{prefix}.log"
    locked = tmp_path / f"{prefix}_{identity}.log"
    finished = tmp_path / f"{prefix}_{'b' * 64}.log"
    archive = tmp_path / f"{prefix}.2000-01-02_00-00-00.log.zip"
    recent = tmp_path / f"{prefix}_{'c' * 64}.log"
    unowned = tmp_path / "service.log"
    old = time() - LOG_RETENTION_SECONDS - 60
    for path in (active, locked, finished, archive, recent, unowned):
        path.write_text("log")
        if path != recent:
            os.utime(path, (old, old))
    symlink = tmp_path / f"{prefix}_{'d' * 64}.log"
    symlink.symlink_to(finished)
    with locked.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cleanup_log_files(tmp_path)
        assert locked.is_file()
    assert active.is_file()
    assert recent.is_file()
    assert unowned.is_file()
    assert symlink.is_symlink()
    assert not finished.exists()
    assert not archive.exists()
    cleanup_log_files(tmp_path)
    assert not locked.exists()


def test_logging_uses_the_configured_timezone_and_bounds_arguments(tmp_path):
    try:
        configure_logging(LoggingConfig(log_dir=tmp_path, timezone="UTC", log_to_console=False))
        get_logger("test").info("timezone marker")
        content = get_log_path().read_text()
        assert "+00:00" in content
        assert "axonx.test" in content
        assert "timezone marker" in content
        assert format_log_arguments({"x": 1}) == "{'x': 1}"
        rendered = format_log_arguments({"x": "a" * LOG_ARGUMENT_MAX_LENGTH})
        assert len(rendered) == LOG_ARGUMENT_MAX_LENGTH
        assert rendered.endswith("...")
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
