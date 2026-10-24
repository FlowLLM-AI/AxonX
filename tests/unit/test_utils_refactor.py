"""Focused regression tests for shared utility boundaries."""

from __future__ import annotations

import os
import sys
import json
import subprocess
from importlib import import_module
from datetime import datetime, timezone
from textwrap import dedent
from types import SimpleNamespace
from pathlib import Path
from zipfile import ZipFile

import pytest
from loguru import _logger

from axonx.cli.parser import Command
from axonx.plugin.registry import ProviderRegistry
from axonx.config.execution import AXONX_TASK_LOG_DIR, AXONX_TASK_TIMEZONE, AXONX_TASK_WORKSPACE_DIR
from axonx.app.core.composition import compose_application
from axonx.plugin.loading import load_symbol
from axonx.config.env import find_env_file, load_env
from axonx.common.fs import directory_sha256
from axonx.common.logging import LoggingConfig, configure_logging, get_log_path, get_logger
from axonx.task.runtime.logging import task_log_scope
from axonx.app.core.logging import LOG_RETENTION_SECONDS, cleanup_log_files


def test_dotenv_does_not_override_process_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=dotenv\nNEW_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "process")
    monkeypatch.delenv("NEW_VALUE", raising=False)

    assert find_env_file(tmp_path) == env_file
    assert load_env(env_file) == {"EXISTING": "process", "NEW_VALUE": "loaded"}
    assert os.environ["EXISTING"] == "process"


def test_directory_hash_frames_file_contents_unambiguously(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    marker = len(b"b").to_bytes(4, "big") + b"b"
    (one / "a").write_bytes(b"x" + marker)
    (two / "a").write_bytes(b"x")
    (two / "b").write_bytes(b"")

    assert directory_sha256(one) != directory_sha256(two)


def test_directory_hash_refuses_symlinks(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    target = tmp_path / "outside"
    target.write_text("secret", encoding="utf-8")
    try:
        (root / "link").symlink_to(target)
    except OSError:
        pytest.skip("Symlinks are unavailable")

    with pytest.raises(ValueError, match="does not allow symlinks"):
        directory_sha256(root)


def test_directory_hash_preserves_historical_nested_file_order(tmp_path):
    for name, value in {
        "alpha/x.py": "x\n",
        "alpha.py": "alpha\n",
        "alpha/sub/z.py": "z\n",
        "beta/y.py": "y\n",
        "z.txt": "last\n",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    assert directory_sha256(tmp_path) == "42cd22664cb897edb85a76c02b603be2dba2d2ee5b02ae9fe2afecf5b1d92f3e"


def test_symbol_loading_never_reexecutes_an_imported_module(tmp_path, monkeypatch):
    module_name = "axonx_test_plugin_loading"
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text(
        "loads = globals().get('loads', 0) + 1\nclass Candidate: pass\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(module_name, None)

    first = load_symbol(f"{module_name}:Candidate", object, kind="Task")
    second = load_symbol(f"{module_name}:Candidate", object, kind="Task")

    assert first is second
    assert sys.modules[module_name].loads == 1


def test_logging_configuration_is_explicit(tmp_path):
    configure_logging(LoggingConfig(log_dir=tmp_path, log_to_console=False, log_to_file=True))
    get_logger("probe").info("configured")

    path = get_log_path()
    assert path is not None
    assert path.parent == tmp_path.resolve()
    assert "configured" in path.read_text(encoding="utf-8")

    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


@pytest.mark.parametrize("host_timezone", ["UTC", "Asia/Shanghai"])
@pytest.mark.parametrize("log_timezone", [None, "UTC", "America/New_York"])
def test_logging_timezone_is_independent_of_host(tmp_path, host_timezone, log_timezone):
    script = dedent("""
        import json
        import sys
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from axonx.common.logging import LoggingConfig, configure_logging, get_log_path, get_logger

        options = json.loads(sys.argv[2])
        zone = ZoneInfo(options.get("timezone", "Asia/Shanghai"))
        before = datetime.now(zone).replace(microsecond=0)
        configure_logging(LoggingConfig(log_dir=sys.argv[1], **options))
        get_logger("probe").info("timezone probe")
        path = get_log_path()
        after = datetime.now(zone)
        print(json.dumps({"before": before.isoformat(), "after": after.isoformat(),
                          "filename": path.name, "content": path.read_text(encoding="utf-8")}))
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
        """)
    options = {} if log_timezone is None else {"timezone": log_timezone}
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), json.dumps(options)],
        env={**os.environ, "TZ": host_timezone},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    before = datetime.fromisoformat(payload["before"])
    after = datetime.fromisoformat(payload["after"])
    for content in [payload["content"], result.stderr]:
        timestamp = datetime.strptime(content.split(" | ", 1)[0], "%Y-%m-%d %H:%M:%S %z")
        assert before <= timestamp <= after
        assert timestamp.utcoffset() == before.utcoffset()
        assert "timezone probe" in content
    filename_time = datetime.strptime(payload["filename"].rsplit("_", 1)[0], "%Y-%m-%d_%H-%M-%S")
    assert before.replace(tzinfo=None) <= filename_time <= after.replace(tzinfo=None)


def test_logging_rejects_unknown_timezone_without_replacing_sinks(tmp_path):
    configure_logging(LoggingConfig(log_dir=tmp_path, log_to_console=False))
    path = get_log_path()
    try:
        with pytest.raises(ValueError, match="Unknown timezone"):
            configure_logging(LoggingConfig(timezone="Unknown/Timezone"))
        assert get_log_path() == path
        get_logger().info("still configured")
        assert "still configured" in path.read_text(encoding="utf-8")
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_logging_tracks_daylight_saving_after_configuration(monkeypatch, capsys):
    configure_logging(LoggingConfig(timezone="America/New_York", log_to_file=False))
    try:
        for instant in [datetime(2026, 1, 12, 12, tzinfo=timezone.utc), datetime(2026, 7, 12, 12, tzinfo=timezone.utc)]:
            monkeypatch.setattr(_logger, "aware_now", lambda instant=instant: instant)
            get_logger().info("offset probe")
        lines = capsys.readouterr().err.splitlines()
        assert lines[0].startswith("2026-01-12 07:00:00 -05:00 |")
        assert lines[1].startswith("2026-07-12 08:00:00 -04:00 |")
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_logging_rotates_at_configured_midnight(tmp_path, monkeypatch):
    from loguru import _file_sink

    # Freeze file creation and record clocks around Shanghai midnight (16:00 UTC).
    before = datetime(2026, 10, 12, 15, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 10, 12, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(_file_sink, "get_ctime", lambda path: before.timestamp())
    configure_logging(LoggingConfig(log_dir=tmp_path, log_to_console=False))
    try:
        monkeypatch.setattr(_logger, "aware_now", lambda: before)
        get_logger().info("before midnight")
        assert not list(tmp_path.glob("*.zip"))
        monkeypatch.setattr(_logger, "aware_now", lambda: after)
        get_logger().info("after midnight")
        archives = list(tmp_path.glob("*.zip"))
        assert len(archives) == 1
        with ZipFile(archives[0]) as archive:
            assert "before midnight" in archive.read(archive.namelist()[0]).decode("utf-8")
        content = get_log_path().read_text(encoding="utf-8")
        assert "before midnight" not in content
        assert "2026-10-13 00:00:00 +08:00" in content
        assert "after midnight" in content
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_log_retention_cleans_only_expired_axonx_logs(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    old = now - LOG_RETENTION_SECONDS - 1
    monkeypatch.setattr("axonx.app.core.logging.time", lambda: now)
    monkeypatch.setattr("axonx.app.core.logging.psutil.pid_exists", lambda pid: pid == os.getpid())
    expired = [
        tmp_path / "2026-01-01_00-00-00_123.log",
        tmp_path / f"2026-01-01_00-00-00_123_{'a' * 64}.log",
        tmp_path / f"2026-01-01_00-00-00_{os.getpid()}.2026-01-02_00-00-00_000000.log.zip",
    ]
    retained = [
        tmp_path / "2026-01-01_00-00-00_124.log",
        tmp_path / f"2026-01-01_00-00-00_{os.getpid()}.log",
        tmp_path / "update.log",
        tmp_path / "metadata.json",
    ]
    for path in expired + retained:
        path.write_text("keep or expire", encoding="utf-8")
        os.utime(path, (old, old))
    os.utime(retained[0], (now - LOG_RETENTION_SECONDS, now - LOG_RETENTION_SECONDS))
    outside = tmp_path / "outside"
    outside.write_text("preserve", encoding="utf-8")
    link = tmp_path / "2026-01-01_00-00-00_125.log"
    link.symlink_to(outside)
    subdirectory = tmp_path / "nested"
    subdirectory.mkdir()
    nested = subdirectory / expired[0].name
    nested.write_text("preserve", encoding="utf-8")
    os.utime(nested, (old, old))

    cleanup_log_files(tmp_path)

    assert all(not path.exists() for path in expired)
    assert all(path.exists() for path in retained)
    assert link.is_symlink() and outside.read_text(encoding="utf-8") == "preserve"
    assert nested.exists()


def test_worker_logging_does_not_scan_or_clean_shared_logs(tmp_path, monkeypatch):
    path = tmp_path / f"2026-01-01_00-00-00_123_{'a' * 64}.log"
    path.write_text("expired", encoding="utf-8")
    os.utime(path, (0, 0))

    def scan(*_args, **_kwargs):
        pytest.fail("Configuring a worker must not scan the shared log directory")

    monkeypatch.setattr(Path, "glob", scan)
    configure_logging(LoggingConfig(log_dir=tmp_path, log_to_console=False))
    try:
        assert path.exists()
        assert get_log_path().exists()
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_retention_preserves_quiet_active_runs_and_releases_their_locks(tmp_path):
    configure_logging(LoggingConfig(log_dir=tmp_path, log_to_console=False))
    try:
        with task_log_scope("active") as path:
            get_logger().info("before cleanup")
            os.utime(path, (0, 0))
            # A service must honor a worker's lock across process boundaries.
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; import sys; "
                    "from axonx.app.core.logging import cleanup_log_files; "
                    "cleanup_log_files(Path(sys.argv[1]))",
                    str(tmp_path),
                ],
                check=True,
                timeout=10,
            )
            assert path.exists()
            get_logger().info("after cleanup")
        assert "after cleanup" in path.read_text(encoding="utf-8")
        os.utime(path, (0, 0))
        cleanup_log_files(tmp_path)
        assert not path.exists()
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_application_startup_uses_configured_log_timezone(tmp_path, monkeypatch):
    instant = datetime(2026, 10, 12, 7, 47, 25, tzinfo=timezone.utc)
    monkeypatch.setattr(_logger, "aware_now", lambda: instant)
    try:
        compose_application(
            ProviderRegistry(),
            "test",
            {"log_dir": str(tmp_path), "timezone": "UTC", "log_to_console": False},
        )
        content = get_log_path().read_text(encoding="utf-8")
        assert "2026-10-12 07:47:25 +00:00 |" in content
        assert "Initializing AxonX Application" in content
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


@pytest.mark.parametrize("from_environment", [True, False])
def test_exec_worker_uses_same_timezone_for_tasks_and_logs(tmp_path, monkeypatch, from_environment):
    cli = import_module("axonx.cli.main")
    instant = datetime(2026, 10, 12, 7, 47, 25, tzinfo=timezone.utc)
    monkeypatch.setattr(_logger, "aware_now", lambda: instant)
    monkeypatch.setattr(cli, "load_env", lambda **kwargs: None)
    config = {"workspace_dir": str(tmp_path / "workspace"), "log_dir": str(tmp_path), "timezone": "UTC"}
    if from_environment:
        for key, field in [
            (AXONX_TASK_WORKSPACE_DIR, "workspace_dir"),
            (AXONX_TASK_LOG_DIR, "log_dir"),
            (AXONX_TASK_TIMEZONE, "timezone"),
        ]:
            monkeypatch.setenv(key, config[field])
        # Workers with a complete handoff must not resolve service configuration.
        monkeypatch.setattr(cli, "resolve_app_config", lambda **kwargs: pytest.fail("Unexpected config lookup"))
    else:
        for key in [AXONX_TASK_WORKSPACE_DIR, AXONX_TASK_LOG_DIR, AXONX_TASK_TIMEZONE]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(cli, "resolve_app_config", lambda **kwargs: config)

    class Executor:
        def __init__(self, workspace_dir, *, timezone):
            assert workspace_dir == config["workspace_dir"]
            assert timezone == config["timezone"]

        def execute(self, name, inputs):
            get_logger().info("worker probe")
            return SimpleNamespace(output_params={}, exit_code=0)

    monkeypatch.setattr("axonx.task.runtime.TaskExecutor", Executor)
    try:
        assert cli._run_exec(Command("exec", {"task": "demo"})) == 0
        content = get_log_path().read_text(encoding="utf-8")
        assert "2026-10-12 07:47:25 +00:00 |" in content
        assert "worker probe" in content
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
