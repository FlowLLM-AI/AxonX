"""Local execution and cron configuration stay independent of the application."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from axonx.common.constants import AXONX_DEFAULT_LOG_DIR, AXONX_DEFAULT_TIMEZONE
from axonx.common.runtime import AXONX_TASK_LOG_DIR, AXONX_TASK_TIMEZONE, AXONX_TASK_WORKSPACE_DIR

ROOT = Path(__file__).resolve().parents[2]
BLOCK_APP = """
import importlib.abc, sys
class BlockApp(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'axonx.app' or fullname.startswith('axonx.app.'):
            raise AssertionError('Application imported: ' + fullname)
sys.meta_path.insert(0, BlockApp())
"""


@pytest.mark.parametrize(
    "environment,expected",
    [
        ({}, (".axonx", AXONX_DEFAULT_LOG_DIR, AXONX_DEFAULT_TIMEZONE)),
        ({"AXONX_WORKSPACE_DIR": "shared"}, ("shared", AXONX_DEFAULT_LOG_DIR, AXONX_DEFAULT_TIMEZONE)),
        (
            {
                "AXONX_WORKSPACE_DIR": "shared",
                AXONX_TASK_WORKSPACE_DIR: "worker",
                AXONX_TASK_LOG_DIR: "worker-logs",
                AXONX_TASK_TIMEZONE: "UTC",
            },
            ("worker", "worker-logs", "UTC"),
        ),
    ],
)
def test_execution_environment_precedence(tmp_path, monkeypatch, environment, expected):
    cli = importlib.import_module("axonx.cli.main")
    monkeypatch.chdir(tmp_path)
    for name in ("AXONX_WORKSPACE_DIR", AXONX_TASK_WORKSPACE_DIR, AXONX_TASK_LOG_DIR, AXONX_TASK_TIMEZONE):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    logging = []
    monkeypatch.setattr(cli, "configure_logging", logging.append)
    monkeypatch.setattr(cli.ConfigLoader, "resolve", lambda **_: pytest.fail("Unexpected service config lookup"))
    config = cli._execution_config()
    assert (config.workspace_dir, config.log_dir, config.timezone) == expected
    assert (str(logging[0].log_dir), logging[0].timezone) == expected[1:]


def test_exec_and_kill_work_without_application_imports(tmp_path):
    code = BLOCK_APP + """
from axonx.cli import main
from axonx.common.config import ConfigLoader
from axonx.task.storage.workspace import read_entry
from pathlib import Path

def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected service config lookup')
ConfigLoader.load = forbidden
assert main(['exec', '--task', 'demo', '--task-name', 'isolated', '--x', '2', '--y', '3']) == 0
status = read_entry(Path('workspace'), 'base#demo#isolated')
assert status.output_params['result'] == 5
assert main(['kill', '--task-id', status.task_id, '--run-id', status.run_id]) == 0
assert not any(name == 'axonx.app' or name.startswith('axonx.app.') for name in sys.modules)
"""
    (tmp_path / ".env").write_text("AXONX_WORKSPACE_DIR=workspace\nAXONX_TASK_LOG_DIR=logs\nAXONX_TASK_TIMEZONE=UTC\n")
    environment = {name: value for name, value in os.environ.items() if not name.startswith("AXONX_")}
    environment["PYTHONPATH"] = str(ROOT)
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=environment, check=True, timeout=20)


def test_cron_worker_loads_configuration_without_app_or_task_imports(tmp_path):
    (tmp_path / "tasks.cron").write_text("* * * * * axonx exec --task demo\n")
    (tmp_path / "app.yaml").write_text(
        "cron: tasks.cron\nworkspace_dir: work\nlog_dir: logs\ntimezone: UTC\nservice: {backend: http}\n"
    )
    code = BLOCK_APP + """
import importlib, os
cli = importlib.import_module('axonx.cli.main')
os.environ[cli.daemon.ROLE] = 'cron'
async def run(source, config):
    scheduler = cli._cron(source, config)
    assert len(scheduler.entries) == 1
    assert config.workspace_dir == 'work'
    assert config.timezone == 'UTC'
cli._run_cron = run
assert cli.main(['start', '--config', 'app.yaml']) == 0
assert not any(name == 'axonx.task' or name.startswith('axonx.task.') for name in sys.modules)
"""
    subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(ROOT)}, check=True, timeout=20
    )
