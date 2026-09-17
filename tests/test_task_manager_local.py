"""Unit tests for local Task manager support services."""

# pylint: disable=missing-function-docstring

from datetime import UTC, datetime, timedelta
import json
import os

from axonx.components.task_manager.local.logs import TaskLogLocator
from axonx.components.task_manager.local.reconciliation import TaskStateReconciler, WorkerExit
from axonx.components.task_manager.local.repository import TaskStatusRepository
from axonx.enums import TaskState, TaskType
from axonx.schema import TaskStatus
from axonx.task.common import DemoTask
from axonx.task.runner import TaskRunner


def test_status_repository_round_trips_snapshots(tmp_path):
    repository = TaskStatusRepository(tmp_path, version=2)
    status = TaskStatus(
        task_id="analysis#saved",
        task_type=TaskType.ANALYSIS,
        state=TaskState.SUCCEEDED,
    )

    repository.save([status])
    loaded = repository.load()

    assert loaded is not None
    assert loaded.should_save is True
    assert loaded.foreign_workspace is None
    assert loaded.statuses == {status.task_id: status}


def test_status_repository_ignores_other_versions_without_rewriting(tmp_path):
    repository = TaskStatusRepository(tmp_path, version=2)
    repository.directory.mkdir(parents=True, exist_ok=True)
    repository.path.write_text(json.dumps({"version": 1, "tasks": []}), encoding="utf-8")

    loaded = repository.load()

    assert loaded is not None
    assert not loaded.statuses
    assert loaded.should_save is False


def test_log_locator_sanitizes_and_backfills_loaded_paths(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    expected = log_dir / "worker_42.log"
    expected.write_text("log", encoding="utf-8")
    locator = TaskLogLocator(log_dir)
    status = TaskStatus(
        task_id="analysis#legacy",
        task_type=TaskType.ANALYSIS,
        pid=42,
        log_path=str(tmp_path / "outside.log"),
    )

    locator.prepare_loaded({status.task_id: status})

    assert status.log_path == str(expected)


def test_reconciler_applies_exit_that_arrives_before_first_status():
    reconciler = TaskStateReconciler()
    occurred_at = datetime.now(UTC)
    assert reconciler.record_exit({}, WorkerExit(42, -9, "no stderr output", occurred_at)) is False
    incoming = TaskStatus(
        task_id="analysis#late",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
        pid=42,
    )

    accepted = reconciler.accept(incoming.task_id, None, incoming)

    assert accepted is not None
    assert accepted.state == TaskState.FAILED
    assert accepted.exit_code == 137
    assert accepted.finished_at == occurred_at
    assert accepted.error == "Worker terminated by signal SIGKILL (9)"


def test_reconciler_rejects_late_status_after_cancellation():
    reconciler = TaskStateReconciler()
    current = TaskStatus(
        task_id="analysis#cancelled",
        task_type=TaskType.ANALYSIS,
        state=TaskState.CANCELLED,
    )
    incoming = current.model_copy(update={"state": TaskState.SUCCEEDED})

    assert reconciler.accept(current.task_id, current, incoming) is None


def test_reconciler_accepts_rerun_and_rejects_previous_process_reports():
    reconciler = TaskStateReconciler()
    task_id = "analysis#fixed"
    old = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.SUCCEEDED, pid=41)
    new = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.QUEUED, pid=42)

    accepted = reconciler.accept(task_id, old, new)
    assert accepted is not None and accepted.pid == 42
    assert reconciler.accept(task_id, accepted, old) is None
    assert reconciler.accept(task_id, accepted, new.model_copy(update={"state": TaskState.RUNNING})) is not None


def test_reconciler_accepts_rerun_after_cancellation():
    reconciler = TaskStateReconciler()
    task_id = "analysis#fixed"
    cancelled = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.CANCELLED, pid=41)
    new = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=42)

    accepted = reconciler.accept(task_id, cancelled, new)
    assert accepted is not None and accepted.pid == 42
    assert reconciler.accept(task_id, accepted, cancelled) is None


def test_reconciler_accepts_rerun_after_deletion():
    reconciler = TaskStateReconciler()
    task_id = "analysis#fixed"
    old = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.SUCCEEDED, pid=41)
    new = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.QUEUED, pid=42)
    reconciler.mark_deleted(old)

    assert reconciler.accept(task_id, None, old) is None
    accepted = reconciler.accept(task_id, None, new)
    assert accepted is not None and accepted.pid == 42
    assert reconciler.accept(task_id, accepted, old) is None


def test_reconciler_accepts_recycled_pid_for_new_execution():
    reconciler = TaskStateReconciler()
    task_id = "analysis#fixed"
    first = TaskStatus(
        task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.SUCCEEDED,
        pid=41, execution_id="first",
    )
    second = TaskStatus(
        task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.SUCCEEDED,
        pid=42, execution_id="second",
    )
    third = TaskStatus(
        task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING,
        pid=41, execution_id="third",
    )

    assert reconciler.accept(task_id, first, second) is not None
    accepted = reconciler.accept(task_id, second, third)
    assert accepted is not None and accepted.execution_id == "third"
    assert reconciler.accept(task_id, accepted, first) is None
    assert reconciler.accept(task_id, accepted, second) is None
    assert reconciler.accept(task_id, accepted, third.model_copy(update={"state": TaskState.SUCCEEDED})) is not None


def test_reconciler_ignores_pending_exit_from_prior_use_of_pid():
    reconciler = TaskStateReconciler()
    exited_at = datetime.now(UTC)
    reconciler.record_exit({}, WorkerExit(41, 1, "old failure", exited_at))
    new = TaskStatus(
        task_id="analysis#fixed", task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING, pid=41, execution_id="new",
        started_at=exited_at + timedelta(seconds=1),
    )

    accepted = reconciler.accept(new.task_id, None, new)
    assert accepted is not None and accepted.state == TaskState.RUNNING


def test_reconciler_ignores_old_exit_during_real_rerun_status_sequence(tmp_path):
    reconciler = TaskStateReconciler()
    task_id = "base#demo#fixed"
    old = TaskStatus(
        task_id=task_id, task_type=TaskType.BASE, state=TaskState.SUCCEEDED,
        pid=os.getpid(), execution_id="old",
    )
    exited_at = datetime.now(UTC)
    reconciler.record_exit({task_id: old}, WorkerExit(os.getpid(), 1, "old failure", exited_at))
    task = DemoTask(
        {"x": 1, "y": 2, "task_name": "fixed", "include_time": False},
        workspace_path=tmp_path,
    )
    assert task.created_at > exited_at
    accepted = []
    current = old

    def receive(status):
        nonlocal current
        current = reconciler.accept(task_id, current, status)
        assert current is not None
        accepted.append(current)

    TaskRunner(receive).run(task)

    assert accepted[0].state == TaskState.QUEUED
    assert accepted[1].state == TaskState.RUNNING
    assert accepted[-1].state == TaskState.SUCCEEDED
    assert all(status.execution_id == task.status.execution_id for status in accepted)
