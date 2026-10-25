"""Exact process identity, durable reconciliation, and explicit termination."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import psutil
import pytest
from pydantic import ValidationError

from axonx.common.process import machine_id, process_started_at
from axonx.task.builtins.demo import DemoTask
from axonx.task.enums import TaskState
from axonx.task.runtime import TaskExecutor
from axonx.task.runtime.runner import TaskRunner
from axonx.task.schemas.lifecycle import ChildTaskRecord, TaskMetadata
from axonx.task.storage import records
from axonx.task.storage.index import scan_metadata
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata


@contextmanager
def child_process():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def record(root, name="sample", child=None, **kwargs):
    pid = child.pid if child else __import__("os").getpid()
    metadata = TaskMetadata(
        version=1,
        task_id=f"base#demo#{name}",
        run_id=uuid4().hex,
        task_type="base",
        machine_id=machine_id(),
        pid=pid,
        process_started_at=process_started_at(pid),
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        **kwargs,
    )
    directory = task_path(root, metadata.task_id)
    directory.mkdir(parents=True, exist_ok=True)
    write_task_metadata(directory, metadata)
    return metadata


def test_metadata_requires_process_identity():
    with pytest.raises(ValidationError) as error:
        TaskMetadata(version=1, task_id="base#demo#sample", run_id="sample", task_type="base")
    assert {item["loc"][0] for item in error.value.errors()} == {"machine_id", "pid", "process_started_at"}


def test_first_record_is_running_with_identity(tmp_path, monkeypatch):
    publications = []
    original = __import__("axonx.task.runtime.runner", fromlist=["write_task_metadata"]).write_task_metadata
    monkeypatch.setattr(
        "axonx.task.runtime.runner.write_task_metadata",
        lambda path, item: (publications.append(item.model_copy(deep=True)), original(path, item))[-1],
    )
    status = TaskExecutor(tmp_path).execute("demo", {"task_name": "first", "x": 1, "y": 2})
    assert status.state == TaskState.SUCCEEDED
    assert publications[0].state == TaskState.RUNNING
    assert publications[0].started_at and publications[0].machine_id and publications[0].pid


def test_unchanged_file_is_rechecked_after_process_exit(tmp_path):
    with child_process() as child:
        status = record(tmp_path, child=child)
        status.children.append(
            ChildTaskRecord(node_name="constructing", attempt=1, task="demo", run_id="not-yet-bound")
        )
        write_task_metadata(task_path(tmp_path, status.task_id), status)
        first, versions = scan_metadata(tmp_path, {}, {})
        assert first[status.task_id].state == TaskState.RUNNING
        child.kill()
        child.wait(timeout=5)
        refreshed, _ = scan_metadata(tmp_path, first, versions)
    assert refreshed[status.task_id].state == TaskState.FAILED
    assert refreshed[status.task_id].children[0].state == TaskState.FAILED
    assert read_entry(tmp_path, status.task_id).state == TaskState.FAILED
    assert read_entry(tmp_path, status.task_id).finished_at is not None


def test_foreign_replicas_and_unverifiable_processes_are_unchanged(tmp_path, monkeypatch):
    status = record(tmp_path)
    directory = task_path(tmp_path, status.task_id)
    foreign = status.model_copy(update={"machine_id": "another-machine"})
    write_task_metadata(directory, foreign)
    assert records.reconcile_task(directory, foreign.run_id) == foreign
    write_task_metadata(directory, status)
    monkeypatch.setattr(records, "process_instance", lambda *_: (_ for _ in ()).throw(psutil.AccessDenied(status.pid)))
    assert records.reconcile_task(directory, status.run_id) == status


def test_reused_pid_is_not_signalled(tmp_path):
    status = record(tmp_path)
    directory = task_path(tmp_path, status.task_id)
    status.process_started_at -= timedelta(seconds=10)
    write_task_metadata(directory, status)
    result = records.kill_task(tmp_path, status.task_id, status.run_id)
    assert result.state == TaskState.FAILED
    assert "PID was reused" in result.error


def test_observer_never_settles_replacement_run(tmp_path):
    previous = record(tmp_path)
    replacement = record(tmp_path)
    result = records.reconcile_task(task_path(tmp_path, previous.task_id), previous.run_id)
    assert result.run_id == replacement.run_id and result.state == TaskState.RUNNING


def test_live_conflict_reports_exact_kill_command(tmp_path):
    previous = record(tmp_path)
    with pytest.raises(FileExistsError) as error:
        TaskExecutor(tmp_path).execute("demo", {"task_name": "sample", "x": 1, "y": 2})
    assert f"--run-id {previous.run_id}" in str(error.value)
    assert "axonx kill" in str(error.value)
    assert read_entry(tmp_path, previous.task_id) == previous


def test_dead_run_can_be_overwritten_and_persistent_data_survives(tmp_path):
    with child_process() as child:
        previous = record(tmp_path, child=child)
        directory = task_path(tmp_path, previous.task_id)
        (directory / "persistent").mkdir()
        (directory / "persistent/data").write_text("retained")
        (directory / "obsolete").write_text("old run")
        child.kill()
        child.wait(timeout=5)
        status = TaskExecutor(tmp_path).execute("demo", {"task_name": "sample", "x": 1, "y": 2})
    assert status.state == TaskState.SUCCEEDED and status.run_id != previous.run_id
    assert (directory / "persistent/data").read_text() == "retained"
    assert not (directory / "obsolete").exists()


def test_explicit_kill_stops_real_process_and_reconciles_children(tmp_path):
    with child_process() as child:
        parent = record(tmp_path, "parent", child)
        nested = record(tmp_path, "nested", child, parent_run_id=parent.run_id)
        parent.children.append(
            ChildTaskRecord(node_name="nested", attempt=1, task="demo", task_id=nested.task_id, run_id=nested.run_id)
        )
        write_task_metadata(task_path(tmp_path, parent.task_id), parent)
        result = records.kill_task(tmp_path, nested.task_id, nested.run_id)
        child.wait(timeout=5)
    assert result.task_id == parent.task_id and result.state == TaskState.FAILED
    assert read_entry(tmp_path, nested.task_id).state == TaskState.FAILED
    assert read_entry(tmp_path, parent.task_id).children[0].state == TaskState.FAILED


def test_foreign_kill_and_wrong_run_are_refused(tmp_path):
    with child_process() as child:
        status = record(tmp_path, child=child)
        status.machine_id = "foreign"
        write_task_metadata(task_path(tmp_path, status.task_id), status)
        with pytest.raises(ValueError, match="this machine"):
            records.kill_task(tmp_path, status.task_id, status.run_id)
        with pytest.raises(ValueError, match="run_id"):
            records.kill_task(tmp_path, status.task_id, "different")
        assert child.poll() is None


def test_invalid_kill_options_do_not_signal(tmp_path):
    with child_process() as child:
        status = record(tmp_path, child=child)
        with pytest.raises(ValueError, match="timeout"):
            records.kill_task(tmp_path, status.task_id, status.run_id, timeout=-1)
        assert child.poll() is None


def test_initial_publication_serializes_competing_runs(tmp_path, monkeypatch):
    inside, publish = Event(), Event()
    original = TaskRunner._prepare_directory

    def prepare(runner, task):
        original(runner, task)
        inside.set()
        assert publish.wait(3)

    monkeypatch.setattr(TaskRunner, "_prepare_directory", prepare)
    first = DemoTask({"task_name": "race", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    second = DemoTask({"task_name": "race", "x": 3, "y": 4}, workspace_path=tmp_path, reg_name="demo")
    with ThreadPoolExecutor(2) as pool:
        running = pool.submit(TaskRunner().run, first)
        assert inside.wait(3)
        competing = pool.submit(TaskRunner().run, second)
        with pytest.raises(FutureTimeout):
            competing.result(timeout=0.05)
        publish.set()
        running.result(timeout=5)
        # A competitor may observe either running or the already-terminal record;
        # in the latter case overwrite is allowed only after the first completes.
        try:
            result = competing.result(timeout=5)
        except FileExistsError:
            result = read_entry(tmp_path, first.task_id)
        assert result.state == TaskState.SUCCEEDED


def test_app_import_does_not_load_plugins_or_executable_tasks():
    code = """import sys
from axonx.app import Application
Application(log_to_console=False, log_to_file=False)
assert not any(n == 'axonx.plugin' or n.startswith('axonx.plugin.') for n in sys.modules)
assert not any(n.startswith(('axonx.task.builtins', 'axonx.task.runtime', 'axonx.task.catalog')) for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)


def test_transaction_files_are_hidden_and_protected(tmp_path):
    from axonx.app.core import Application

    workspace = Application(workspace_dir=str(tmp_path), log_to_console=False, log_to_file=False).workspace

    metadata = record(tmp_path)
    with records.record_lock(task_path(tmp_path, metadata.task_id)):
        pass
    assert ".task-records" not in {entry["name"] for entry in workspace.list_entries()["entries"]}
    with pytest.raises(ValueError, match="transaction"):
        workspace.delete_entries([".task-records"])


def test_force_is_explicit_and_timeout_preserves_running_record(tmp_path):
    child = subprocess.Popen(  # pylint: disable=consider-using-with
        [
            sys.executable,
            "-u",
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        metadata = record(tmp_path, child=child)
        with pytest.raises(TimeoutError):
            records.kill_task(tmp_path, metadata.task_id, metadata.run_id, timeout=0.05)
        assert child.poll() is None
        assert read_entry(tmp_path, metadata.task_id).state == TaskState.RUNNING
        assert records.kill_task(tmp_path, metadata.task_id, metadata.run_id, force=True).state == TaskState.FAILED
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        child.stdout.close()


def test_kill_preserves_a_run_created_after_old_process_exit(tmp_path, monkeypatch):
    wait = records.wait_processes
    replacement = []
    with child_process() as child:
        metadata = record(tmp_path, child=child)

        def replace(processes, timeout):
            wait(processes, timeout)
            if processes:
                replacement.append(record(tmp_path))

        monkeypatch.setattr(records, "wait_processes", replace)
        with pytest.raises(ValueError, match="replacement was left unchanged"):
            records.kill_task(tmp_path, metadata.task_id, metadata.run_id)
        assert read_entry(tmp_path, metadata.task_id) == replacement[0]


def test_descendant_timeout_keeps_root_available_for_force_retry(tmp_path):
    from axonx.common.process import process_instance

    child_code = (
        "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"
    )
    program = (
        "import subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-u','-c',{child_code!r}],stdout=subprocess.PIPE,text=True); "
        "child.stdout.readline(); print(child.pid,flush=True); time.sleep(60)"
    )
    descendant = None
    with subprocess.Popen([sys.executable, "-u", "-c", program], stdout=subprocess.PIPE, text=True) as child:
        try:
            pid = int(child.stdout.readline().strip())
            started = process_started_at(pid)
            descendant = (pid, started)
            metadata = record(tmp_path, child=child)
            with pytest.raises(TimeoutError):
                records.kill_task(tmp_path, metadata.task_id, metadata.run_id, timeout=0.1)
            assert child.poll() is None
            assert process_instance(pid, started) is not None
            assert records.kill_task(tmp_path, metadata.task_id, metadata.run_id, force=True).state == TaskState.FAILED
            child.wait(timeout=5)
            assert process_instance(pid, started) is None
        finally:
            if descendant and (process := process_instance(*descendant)) is not None:
                process.kill()
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


def test_removed_plugin_and_queue_contracts_are_rejected():
    from axonx.app.config import ApplicationConfig
    from axonx.plugin.manifest import parse_plugin_manifest

    with pytest.raises(ValidationError):
        ApplicationConfig(plugins={"sources": ["obsolete"]})
    with pytest.raises(ValueError, match="invalid"):
        parse_plugin_manifest("tasks: {}\ncomponents: {}", "obsolete")
    with pytest.raises(ValidationError):
        TaskMetadata(
            version=1,
            task_id="base#demo#sample",
            task_type="base",
            run_id="sample",
            state="queued",
            machine_id="local",
            pid=1234,
            process_started_at="2026-01-01T00:00:00Z",
        )


def test_replica_child_cannot_stop_original_parent(tmp_path):
    from axonx.task.schemas.replica import DisplayReplica

    with child_process() as child:
        parent = record(tmp_path, "original", child)
        nested = record(tmp_path, "replica", child, parent_run_id=parent.run_id)
        nested.replica = DisplayReplica(purpose="display", source_digest="a" * 64, policy_digest="b" * 64, files={})
        write_task_metadata(task_path(tmp_path, nested.task_id), nested)
        with pytest.raises(ValueError, match="original Run"):
            records.kill_task(tmp_path, nested.task_id, nested.run_id)
        assert child.poll() is None


def test_process_exit_during_descendant_scan_is_reconciled(tmp_path, monkeypatch):
    from axonx.common.process import process_instance

    with child_process() as child:
        metadata = record(tmp_path, child=child)
        process = process_instance(child.pid, metadata.process_started_at)

        def exited(**_):
            child.kill()
            child.wait(timeout=5)
            raise psutil.NoSuchProcess(child.pid)

        monkeypatch.setattr(process, "children", exited)
        calls = iter([process, None, None])
        monkeypatch.setattr(records, "process_instance", lambda *_: next(calls, None))
        assert records.kill_task(tmp_path, metadata.task_id, metadata.run_id).state == TaskState.FAILED
