"""Recover interrupted local Runs without touching another execution machine."""

import plistlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from axonx.task.builtins import DemoTask
from axonx.task.runtime import process
from axonx.task.runtime.runner import TaskRunner
from axonx.task.schemas.lifecycle import TaskMetadata
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata


def record(root, name, **kwargs):
    values = {
        "state": "running",
        "pid": 2**30,
        "machine_id": process.machine_id(),
        "process_started_at": datetime.now(UTC),
    }
    values.update(kwargs)
    status = TaskMetadata(version=1, task_id=f"base#demo#{name}", run_id=name, task_type="base", **values)
    directory = task_path(root, status.task_id)
    directory.mkdir(parents=True)
    write_task_metadata(directory, status)
    return status


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_machine_id_survives_service_restarts_and_does_not_use_hostname(monkeypatch, platform):
    process.machine_id.cache_clear()
    monkeypatch.setattr(process.sys, "platform", platform)
    identifier = "8e73d5b329b24c0c9b3917c0ca590e42"
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: identifier)
    monkeypatch.setattr(
        process.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=plistlib.dumps([{"IOPlatformUUID": identifier}])),
    )
    try:
        first = process.machine_id()
        process.machine_id.cache_clear()
        assert process.machine_id() == first
        assert first != identifier
        identifier = "809334f970c74deea0453c252a2273ef"
        process.machine_id.cache_clear()
        assert process.machine_id() != first
    finally:
        process.machine_id.cache_clear()


def test_machine_id_uses_linux_fallback_and_rejects_missing_identity(monkeypatch):
    process.machine_id.cache_clear()
    monkeypatch.setattr(process.sys, "platform", "linux")

    def read(path, **_kwargs):
        if str(path) == "/etc/machine-id":
            raise FileNotFoundError(path)
        return "8e73d5b329b24c0c9b3917c0ca590e42"

    monkeypatch.setattr(Path, "read_text", read)
    try:
        assert process.machine_id()
        process.machine_id.cache_clear()
        monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: "")
        with pytest.raises(RuntimeError, match="no OS machine ID"):
            process.machine_id()
    finally:
        process.machine_id.cache_clear()


def test_runner_persists_machine_and_process_identity(tmp_path):
    task = DemoTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    status = TaskRunner().run(task)
    assert status.machine_id == process.machine_id()
    assert status.process_started_at == process.process_started_at()
    assert read_entry(tmp_path, task.task_id) == status
    assert not (tmp_path / ".locks").exists()
