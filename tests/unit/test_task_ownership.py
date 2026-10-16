"""Shared records are observable; only supervised Runs are controllable."""

import asyncio
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from axonx.components.updater.manager import RESPONSE_CALLBACKS
from axonx.core import Application
from axonx.task.query.summary import managed_runs
from axonx.task.schemas.lifecycle import ChildTaskRecord, ScheduleTrigger, TaskMetadata, TaskSource
from axonx.task.storage.locking import workspace_lock, workspace_mutation
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata
from axonx.workspace.browser import delete_workspace_entries


def application(root, port=1024):
    return Application(
        workspace_dir=str(root),
        log_dir=str(root / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "task_manager": {"default": {"backend": "local"}},
            "updater": {"default": {"backend": "local"}},
        },
        jobs={"heartbeat": {"steps": []}},
        schedules={"daily": {"job": "heartbeat", "cron": "0 0 * * *"}},
        service={"backend": "http", "port": port, "web_enabled": False},
    )


def record(root, name, **kwargs):
    status = TaskMetadata(version=1, task_id=f"base#demo#{name}", run_id=name, task_type="base", **kwargs)
    directory = task_path(root, status.task_id)
    directory.mkdir(parents=True)
    write_task_metadata(directory, status)
    return status


def test_child_ownership_requires_exact_run_and_same_worker(tmp_path):
    parent = record(tmp_path, "parent", pid=123)
    child = record(tmp_path, "child", pid=123)
    replaced = record(tmp_path, "replaced", pid=123)
    foreign = record(tmp_path, "foreign", pid=456)
    for status in [child, replaced, foreign]:
        parent.children.append(
            ChildTaskRecord(
                node_name=status.run_id,
                attempt=1,
                task="demo",
                task_id=status.task_id,
                run_id="old" if status is replaced else status.run_id,
            )
        )
    entries = {status.task_id: status for status in [parent, child, replaced, foreign]}
    assert managed_runs(entries, {parent.run_id}) == {"parent": "parent", "child": "parent"}


async def test_two_instances_project_ownership_without_persisting_it(tmp_path):
    status = record(tmp_path, "owned", state="running")
    async with application(tmp_path) as first, application(tmp_path, 1025) as second:
        owner = first.context.components["task_manager"]["default"]
        observer = second.context.components["task_manager"]["default"]
        owner._supervisor.run_pids[status.run_id] = 123
        assert (await owner.get_status(status.task_id)).managed_run_id == status.run_id
        assert (await observer.get_status(status.task_id)).managed_run_id is None
        assert (await owner.list_summaries())[0].managed_run_id == status.run_id
        assert (await observer.list_summaries())[0].managed_run_id is None
        with pytest.raises(RuntimeError, match="unmanaged Run"):
            await observer.cancel(run_id=status.run_id)
    assert read_entry(tmp_path, status.task_id) == status
    assert "managed_run_id" not in (task_path(tmp_path, status.task_id) / "metadata.json").read_text()


async def test_active_scheduled_job_blocks_only_its_own_service_and_admission_recovers(tmp_path, monkeypatch):
    async with application(tmp_path) as first, application(tmp_path, 1025) as second:
        scheduler = first.context.schedulers["daily"]
        updater = first.context.components["updater"]["default"]
        entered, release = asyncio.Event(), asyncio.Event()

        async def run(*_args, **_kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(success=True, answer=None)

        monkeypatch.setattr(first.context.dispatcher, "run", run)
        await scheduler._trigger()
        await entered.wait()
        assert (await updater.restart_blockers())[0]["schedule"] == "daily"
        assert await second.context.components["updater"]["default"].restart_blockers() == []
        first.context.service.restart_arguments = ["start"]
        first.context.service.server = SimpleNamespace()
        monkeypatch.setattr(updater, "_plan", lambda *_: {})
        token = RESPONSE_CALLBACKS.set([])
        try:
            with pytest.raises(RuntimeError, match="scheduled Tasks or Jobs"):
                await updater.request("restart", force=True)
            assert not first.context.metadata.get("maintenance")
        finally:
            RESPONSE_CALLBACKS.reset(token)
            release.set()
        await asyncio.gather(*scheduler._executions)
        assert scheduler.describe()["running"] == 0
        first.context.metadata["maintenance"] = True
        await scheduler._trigger()
        assert not scheduler._executions


async def test_foreign_scheduled_records_do_not_block_and_same_names_have_distinct_ids(tmp_path):
    async with application(tmp_path) as first, application(tmp_path, 1025) as second:
        scheduler = first.context.schedulers["daily"]
        other = second.context.schedulers["daily"]
        assert scheduler.scheduler_id != other.scheduler_id
        source = TaskSource(
            schedule=ScheduleTrigger(
                name=scheduler.name,
                job="heartbeat",
                trigger_id="trigger",
                triggered_at=datetime.now(UTC),
                scheduler_id=scheduler.scheduler_id,
            )
        )
        record(tmp_path, "foreign", state="running", source=source)
        await second.context.components["task_repository"]["default"].reconcile()
        assert await second.context.components["updater"]["default"].restart_blockers() == []


@pytest.mark.parametrize("path", ["base", "base/base#demo#active", "base/base#demo#active/metadata.json"])
def test_workspace_delete_protects_active_tasks_and_ancestors(tmp_path, path):
    status = record(tmp_path, "active", state="running")
    with pytest.raises(ValueError, match="active Task"):
        delete_workspace_entries(tmp_path, [path])
    assert read_entry(tmp_path, status.task_id) == status


async def test_terminal_directory_is_protected_until_other_process_releases_it(tmp_path):
    status = record(tmp_path, "terminal", state="succeeded")
    script = (
        "import sys; from pathlib import Path; from axonx.task.storage.locking import workspace_lock; "
        "lease = workspace_lock(Path(sys.argv[1]), sys.argv[2]); lease.__enter__(); "
        "print('ready', flush=True); sys.stdin.read(1); lease.__exit__(None, None, None)"
    )
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(tmp_path),
        status.task_id,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        assert await asyncio.wait_for(worker.stdout.readline(), 10) == b"ready\n"
        async with application(tmp_path) as app:
            manager = app.context.components["task_manager"]["default"]
            assert await manager.delete([status.task_id]) == []
            assert not await manager.repository.reset_terminal(status.task_id)
            with pytest.raises(BlockingIOError):
                delete_workspace_entries(tmp_path, ["base"])
        assert read_entry(tmp_path, status.task_id) == status
    finally:
        worker.stdin.close()
        await asyncio.wait_for(worker.wait(), 10)
    async with application(tmp_path) as app:
        assert await app.context.components["task_manager"]["default"].delete([status.task_id]) == [status.task_id]


async def test_mutation_wait_is_cancellable_and_does_not_block_event_loop(tmp_path):
    with workspace_lock(tmp_path):

        async def mutate():
            async with workspace_mutation(tmp_path):
                pytest.fail("The first mutation still owns the lock")

        pending = asyncio.create_task(mutate())
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    with workspace_lock(tmp_path):
        pass
    with pytest.raises(ValueError, match="lock files"):
        delete_workspace_entries(tmp_path, [".locks"])


async def test_shared_workspace_update_records_are_isolated(tmp_path):
    first, second = application(tmp_path), application(tmp_path, 1025)
    owner = first.context.components["updater"]["default"]
    observer = second.context.components["updater"]["default"]
    from axonx.components.updater.worker import save

    folder = owner.directory / ("a" * 32)
    folder.mkdir(parents=True)
    save(folder / "record.json", {"phase": "building"})
    await observer.start()
    try:
        assert observer.status()["record"] is None
        assert owner.status()["record"]["phase"] == "building"
    finally:
        await observer.close()


async def test_stopping_manager_rejects_launch_before_worker_handoff(tmp_path, monkeypatch):
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        manager._accepting = False
        launch = AsyncMock()
        monkeypatch.setattr(manager._supervisor, "spawn", launch)
        # A rejected launch must not create a queued record.
        monkeypatch.setattr(manager, "_prepare_task", lambda *_: SimpleNamespace())
        with pytest.raises(RuntimeError, match="stopping"):
            await manager.submit(["--task", "demo"])
        launch.assert_not_awaited()
        assert await manager.list_statuses() == []


async def test_legacy_update_records_remain_readable_without_recovery(tmp_path):
    from axonx.components.updater.worker import save

    update_id = "a" * 32
    folder = tmp_path / "updates" / update_id
    folder.mkdir(parents=True)
    save(folder / "record.json", {"phase": "building"})
    updater = application(tmp_path).context.components["updater"]["default"]
    await updater.start()
    try:
        assert updater.status()["record"] is None
        assert updater.status(update_id)["record"]["phase"] == "building"
    finally:
        await updater.close()


async def test_foreign_workspace_mutation_does_not_block_manager_shutdown(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        waiting = asyncio.Event()

        @asynccontextmanager
        async def mutation(root):
            waiting.set()
            async with workspace_mutation(root):
                yield

        monkeypatch.setattr("axonx.components.task_manager.local.manager.workspace_mutation", mutation)
        monkeypatch.setattr(manager, "_prepare_task", lambda *_: SimpleNamespace())
        with workspace_lock(tmp_path):
            submission = asyncio.create_task(manager.submit(["--task", "demo"]))
            try:
                await asyncio.wait_for(waiting.wait(), 2)
                await asyncio.wait_for(manager.close(), 0.5)
            finally:
                submission.cancel()
                await asyncio.gather(submission, return_exceptions=True)


async def test_cancelled_queue_publication_does_not_leave_an_unmanaged_queued_run(tmp_path, monkeypatch):
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        task = SimpleNamespace(
            task_id="base#demo#cancelled",
            task_type="base",
            is_generated_name=True,
            report_kind=None,
            input_params=SimpleNamespace(model_dump=lambda **_: {}),
            created_at=datetime.now(UTC),
        )
        monkeypatch.setattr(manager, "_prepare_task", lambda *_: task)
        put = manager.repository.put_metadata
        published = asyncio.Event()

        async def interrupted(status):
            await put(status)
            published.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(manager.repository, "put_metadata", interrupted)
        submission = asyncio.create_task(manager.submit(["--task", "demo"]))
        await asyncio.wait_for(published.wait(), 2)
        # Allow failure settlement to use the ordinary repository writer.
        monkeypatch.setattr(manager.repository, "put_metadata", put)
        submission.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submission
        status = read_entry(tmp_path, task.task_id)
        assert status.state.is_terminal
        assert await manager.list_managed_run_ids() == []


async def test_cancellation_and_deletion_do_not_invert_process_and_workspace_locks(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    active = record(tmp_path, "active", state="running")
    terminal = record(tmp_path, "terminal", state="succeeded")
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        manager._supervisor.run_pids[active.run_id] = 123
        cancelling, release, deleting = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def cancel_run(_run_id):
            cancelling.set()
            await release.wait()
            return True

        @asynccontextmanager
        async def mutation(root):
            async with workspace_mutation(root):
                if asyncio.current_task().get_name() == "delete":
                    deleting.set()
                yield

        monkeypatch.setattr(manager._supervisor, "cancel_run", cancel_run)
        monkeypatch.setattr("axonx.components.task_manager.local.manager.workspace_mutation", mutation)
        cancellation = asyncio.create_task(manager.cancel(run_id=active.run_id))
        await asyncio.wait_for(cancelling.wait(), 2)
        deletion = asyncio.create_task(manager.delete([terminal.task_id]), name="delete")
        await asyncio.wait_for(deleting.wait(), 2)
        release.set()
        assert await asyncio.wait_for(asyncio.gather(cancellation, deletion), 2) == [True, [terminal.task_id]]
        assert read_entry(tmp_path, active.task_id).state == "cancelled"


async def test_late_settlement_preserves_already_published_terminal_result(tmp_path):
    status = record(tmp_path, "finished", state="succeeded")
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        from axonx.enums import TaskState

        await manager._finish(status.model_copy(update={"state": TaskState.RUNNING}), TaskState.CANCELLED, 130, "late")
        assert read_entry(tmp_path, status.task_id) == status


async def test_cancelled_settlement_drains_publication_before_releasing_workspace_lock(tmp_path, monkeypatch):
    from threading import Event
    from axonx.enums import TaskState

    status = record(tmp_path, "settling", state="running")
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        entered, release = Event(), Event()

        def append(*_args):
            entered.set()
            assert release.wait(5)

        monkeypatch.setattr("axonx.components.task_manager.local.manager.append_progress_snapshots", append)
        settlement = asyncio.create_task(manager._finish(status, TaskState.FAILED, 1, "worker exited"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            settlement.cancel()
            await asyncio.sleep(0)
            with pytest.raises(BlockingIOError), workspace_lock(tmp_path):
                pass
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await settlement
        assert read_entry(tmp_path, status.task_id).state == TaskState.FAILED


async def test_cancelled_worker_exit_is_not_reported_as_a_crash(tmp_path):
    from axonx.components.task_manager.local.supervisor import WorkerExit

    status = record(tmp_path, "cancelled-worker", state="running")
    async with application(tmp_path) as app:
        manager = app.context.components["task_manager"]["default"]
        await manager._handle_worker_exit(WorkerExit(-15, "", status.task_id, status.run_id, cancelled=True))
        result = read_entry(tmp_path, status.task_id)
        assert result.state == "cancelled"
        assert result.exit_code == 130
        assert result.error == "Task cancelled"
