"""Recover interrupted local Runs without touching another execution machine."""

import asyncio
import os
import plistlib
import signal
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from axonx.core import Application
from axonx.components.task_manager.local.manager import LEGACY_HANDOFF_GRACE_SECONDS
from axonx.enums import TaskState
from axonx.task.builtins import DemoTask
from axonx.task.query.summary import managed_runs
from axonx.task.runtime import process
from axonx.task.runtime.runner import TaskRunner
from axonx.task.schemas.lifecycle import ChildTaskRecord, TaskMetadata, TaskSource
from axonx.task.schemas.replica import DisplayReplica
from axonx.task.storage.locking import workspace_lock
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata


def application(root):
    return Application(
        workspace_dir=str(root),
        log_dir=str(root / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "task_manager": {"default": {"backend": "local"}},
        },
    )


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


def test_process_check_distinguishes_dead_reused_and_unknown_processes(monkeypatch):
    started = process.process_started_at()
    assert process.process_is_alive(os.getpid(), started)
    assert not process.process_is_alive(os.getpid(), started - timedelta(seconds=1))
    assert not process.process_is_alive(2**30, started)
    assert process.process_is_alive(None, started)
    assert process.process_is_alive(-1, started)
    assert process.process_is_alive(os.getpid(), None)
    monkeypatch.setattr(process.psutil, "Process", Mock(side_effect=psutil.AccessDenied(123)))
    assert process.process_is_alive(123, started)


@pytest.mark.parametrize("state", ["queued", "running"])
async def test_startup_recovers_only_dead_local_process_instances(tmp_path, monkeypatch, state):
    local = record(tmp_path, "local", state=state)
    foreign = record(tmp_path, "foreign", machine_id="another-machine")
    legacy = record(tmp_path, "legacy", machine_id=None, process_started_at=None, pid=os.getpid(), state=state)
    live = record(tmp_path, "live", pid=os.getpid(), process_started_at=process.process_started_at())
    reused = record(
        tmp_path,
        "reused",
        pid=os.getpid(),
        process_started_at=process.process_started_at() - timedelta(seconds=1),
    )
    unknown = record(tmp_path, "unknown", process_started_at=None)
    finished = record(tmp_path, "finished", state="succeeded")
    replica = record(
        tmp_path,
        "replica",
        replica=DisplayReplica(source_revision="source", policy_revision="policy", files={}),
    )
    probe = Mock(wraps=process.process_is_alive)
    monkeypatch.setattr("axonx.components.task_manager.local.manager.process_is_alive", probe)
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        for status in (local, reused, legacy):
            recovered = await manager.get_status(status.task_id)
            assert recovered.state == "failed"
            assert recovered.finished_at is not None
            assert "interrupted" in recovered.error
            assert recovered.managed_run_id is None
        for status in (foreign, live, unknown, finished, replica):
            assert read_entry(tmp_path, status.task_id) == status
    # Legacy records use execution locks, never a PID that could belong to another host.
    assert probe.call_count == 4


@pytest.mark.parametrize("legacy", [False, True])
async def test_runner_lock_prevents_recovery_even_when_pid_looks_dead(tmp_path, legacy):
    status = record(tmp_path, "locked", machine_id=None if legacy else process.machine_id())
    with workspace_lock(tmp_path, status.task_id):
        async with application(tmp_path):
            assert read_entry(tmp_path, status.task_id) == status


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("changed", [{"run_id": "replacement"}, {"machine_id": "another-machine"}])
async def test_startup_rechecks_run_and_machine_before_settlement(tmp_path, monkeypatch, changed, legacy):
    original = record(tmp_path, "changed", machine_id=None if legacy else process.machine_id())
    replacement = original.model_copy(update=changed)
    app = application(tmp_path)
    manager = app.context.components["task_manager"]["default"]
    settle = manager._settle

    async def replace_before_settle(*args, **kwargs):
        write_task_metadata(task_path(tmp_path, original.task_id), replacement)
        await settle(*args, **kwargs)

    monkeypatch.setattr(manager, "_settle", replace_before_settle)
    async with app:
        assert read_entry(tmp_path, original.task_id) == replacement


@pytest.mark.parametrize("legacy", [False, True])
async def test_recovery_settles_exact_local_children_and_preserves_results(tmp_path, legacy):
    identity = {"machine_id": None, "process_started_at": None} if legacy else {}
    parent = record(tmp_path, "parent", **identity)
    identity = {"machine_id": parent.machine_id, "process_started_at": parent.process_started_at}
    child = record(tmp_path, "child", parent_run_id=parent.run_id, **identity)
    locked = record(tmp_path, "locked", **identity)
    foreign = record(tmp_path, "foreign", machine_id="another-machine")
    succeeded = record(tmp_path, "succeeded", state="succeeded", **identity)
    replaced = record(tmp_path, "replaced", machine_id="another-machine")
    replica = record(
        tmp_path,
        "replica",
        process_started_at=parent.process_started_at,
        replica=DisplayReplica(source_revision="source", policy_revision="policy", files={}),
    )
    for status in (child, foreign, succeeded, replaced, replica, locked):
        parent.children.append(
            ChildTaskRecord(
                node_name=status.run_id,
                attempt=1,
                task="demo",
                task_id=status.task_id,
                run_id="previous" if status is replaced else status.run_id,
                state=status.state,
            )
        )
    write_task_metadata(task_path(tmp_path, parent.task_id), parent)
    retained = task_path(tmp_path, parent.task_id) / "persistent" / "history.txt"
    retained.parent.mkdir()
    retained.write_text("retained")
    with workspace_lock(tmp_path, locked.task_id):
        async with application(tmp_path):
            recovered = read_entry(tmp_path, parent.task_id)
            assert recovered.state == "failed"
            assert recovered.children[0].state == "failed"
            assert read_entry(tmp_path, child.task_id).state == "failed"
            for status in (foreign, succeeded, replaced, replica, locked):
                assert read_entry(tmp_path, status.task_id) == status
            assert recovered.children[-1].state == "running"
            assert retained.read_text() == "retained"


@pytest.mark.parametrize("naive", [False, True])
async def test_legacy_queued_handoff_has_bounded_grace_and_named_retry_recovers(tmp_path, naive):
    created_at = datetime.now(UTC)
    if naive:
        created_at = created_at.replace(tzinfo=None)
    old = record(tmp_path, "queued", machine_id=None, process_started_at=None, state="queued", created_at=created_at)
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        assert read_entry(tmp_path, old.task_id) == old
        argv = ["--task", "demo", "--task-name", "queued", "--x", "1", "--y", "2"]
        with pytest.raises(FileExistsError, match="Active Task already exists"):
            await manager.submit(argv)
        old.created_at -= timedelta(seconds=LEGACY_HANDOFF_GRACE_SECONDS + 1)
        write_task_metadata(task_path(tmp_path, old.task_id), old)
        handle = await manager.submit(argv)
        assert handle.run_id != old.run_id
        result = await asyncio.wait_for(manager.wait(handle.task_id, handle.run_id, 0.01), 15)
        assert result.state == "succeeded"
        assert result.machine_id == process.machine_id()


@pytest.mark.parametrize("offset_days", [-1, 1])
async def test_old_or_invalid_future_legacy_queued_records_do_not_block_startup(tmp_path, offset_days):
    old = record(
        tmp_path,
        "queued",
        machine_id=None,
        state="queued",
        created_at=datetime.now(UTC) + timedelta(days=offset_days),
    )
    async with application(tmp_path):
        recovered = read_entry(tmp_path, old.task_id)
        assert recovered.state == "failed"
        assert recovered.machine_id is None


def test_machine_and_process_identity_prevent_false_child_ownership(tmp_path):
    parent = record(tmp_path, "parent", pid=os.getpid())
    for name, changes in (
        ("foreign", {"machine_id": "another-machine"}),
        ("reused", {"process_started_at": parent.process_started_at - timedelta(seconds=1)}),
    ):
        child = record(tmp_path, name, pid=parent.pid, process_started_at=parent.process_started_at)
        child = child.model_copy(update=changes)
        parent.children = [
            ChildTaskRecord(node_name=name, attempt=1, task="demo", task_id=child.task_id, run_id=child.run_id)
        ]
        assert managed_runs({parent.task_id: parent, child.task_id: child}, {parent.run_id}) == {
            parent.run_id: parent.run_id
        }


def test_runner_persists_machine_and_process_identity(tmp_path):
    task = DemoTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    status = TaskRunner().run(task)
    assert status.machine_id == process.machine_id()
    assert status.process_started_at == process.process_started_at()
    assert read_entry(tmp_path, task.task_id) == status


@pytest.mark.parametrize("replacement_state", ["failed", "queued"])
def test_late_submitted_worker_cannot_restart_recovered_or_replaced_run(tmp_path, replacement_state):
    task = DemoTask(
        {"x": 1, "y": 2, "task_name": "late"},
        workspace_path=tmp_path,
        reg_name="demo",
        run_id="old-run",
        source=TaskSource(kind="submit"),
    )
    status = record(tmp_path, "late", state=replacement_state)
    if replacement_state == "failed":
        status.run_id = task.context.run_id
        write_task_metadata(task.task_dir, status)
    with pytest.raises(FileExistsError, match="no longer owns"):
        TaskRunner(require_handoff=True).run(task)
    assert read_entry(tmp_path, task.task_id) == status


def test_submitted_worker_requires_queued_handoff(tmp_path):
    task = DemoTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo", source=TaskSource(kind="submit"))
    with pytest.raises(FileNotFoundError, match="no queued Run"):
        TaskRunner(require_handoff=True).run(task)
    assert not task.task_dir.exists()


WORKER_SCRIPT = """
import sys
import time
from pathlib import Path
from axonx.task.builtins import DemoTask
from axonx.task.runtime.runner import TaskRunner

class BlockingDemo(DemoTask):
    def initialize(self):
        super().initialize()
        print('ready', flush=True)
        time.sleep(60)

TaskRunner().run(BlockingDemo({'x': 1, 'y': 2, 'task_name': 'killed'},
                            workspace_path=Path(sys.argv[1]), reg_name='demo'))
"""


@pytest.mark.parametrize("legacy", [False, True])
async def test_sigkill_then_restart_recovers_run_and_allows_same_name_submission(tmp_path, legacy):
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        WORKER_SCRIPT,
        str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    task_id = "base#demo#killed"
    try:
        assert await asyncio.wait_for(worker.stdout.readline(), 15) == b"ready\n"
        old = read_entry(tmp_path, task_id)
        assert old.machine_id == process.machine_id()
        assert old.state == "running"
        if legacy:
            old.machine_id = None
            old.process_started_at = None
            write_task_metadata(task_path(tmp_path, task_id), old)
        async with application(tmp_path):
            assert read_entry(tmp_path, task_id) == old
        worker.kill()
        assert await asyncio.wait_for(worker.wait(), 10) == -signal.SIGKILL
        assert read_entry(tmp_path, task_id).state == "running"
        async with application(tmp_path) as app:
            manager = app.context.components["task_manager"]["default"]
            interrupted = await manager.get_status(task_id)
            assert interrupted.run_id == old.run_id
            assert interrupted.state == "failed"
            handle = await manager.submit(["--task", "demo", "--task-name", "killed", "--x", "1", "--y", "2"])
            assert handle.run_id != old.run_id
            result = await asyncio.wait_for(manager.wait(task_id, handle.run_id, 0.01), 15)
            assert result.state == TaskState.SUCCEEDED
            assert result.machine_id == process.machine_id()
            assert result.pid != os.getpid()
    finally:
        if worker.returncode is None:
            worker.kill()
        await worker.wait()


LAUNCHER_SCRIPT = """
import asyncio
import sys
from pathlib import Path
from axonx.core import Application

async def main():
    app = Application(workspace_dir=sys.argv[1], enable_logo=False,
                      log_to_console=False, log_to_file=False,
                      components={'task_repository': {'default': {'backend': 'local'}},
                                  'task_manager': {'default': {'backend': 'local'}}})
    async with app:
        manager = app.context.components['task_manager']['default']
        async def blocked_spawn(*args, **kwargs):
            print('ready', flush=True)
            await asyncio.sleep(60)
        manager._supervisor.spawn = blocked_spawn
        await manager.submit(['--task', 'demo', '--task-name', 'queued', '--x', '1', '--y', '2'])

asyncio.run(main())
"""


async def test_sigkill_during_submission_then_restart_recovers_queued_run(tmp_path):
    launcher = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        LAUNCHER_SCRIPT,
        str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    task_id = "base#demo#queued"
    try:
        assert await asyncio.wait_for(launcher.stdout.readline(), 15) == b"ready\n"
        queued = read_entry(tmp_path, task_id)
        assert queued.state == "queued"
        assert queued.pid == launcher.pid
        assert queued.machine_id == process.machine_id()
        assert queued.process_started_at == process.process_started_at(launcher.pid)
        async with application(tmp_path):
            assert read_entry(tmp_path, task_id) == queued
        launcher.kill()
        assert await asyncio.wait_for(launcher.wait(), 10) == -signal.SIGKILL
        async with application(tmp_path):
            assert read_entry(tmp_path, task_id).state == "failed"
    finally:
        if launcher.returncode is None:
            launcher.kill()
        await launcher.wait()
