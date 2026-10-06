"""Task batch serialization, failure policy and worker ownership."""

import asyncio
import fcntl
from types import SimpleNamespace

import pytest

from axonx.components.job import TaskBatchJob
from axonx.enums import TaskState, TaskType
from axonx.task.runtime.arguments import parse_task_argv
from axonx.task.storage.workspace import TaskStatus


class Manager:
    def __init__(self, fail=None, block=False):
        self.calls = []
        self.fail = fail
        self.block = block
        self.started = asyncio.Event()
        self.released = asyncio.Event()
        self.cancelled = []
        self.statuses = {}
        self.active = 0
        self.max_active = 0

    async def submit(self, argv):
        name, config = parse_task_argv(argv)
        self.calls.append((name, config))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        status = TaskStatus(
            task_id=f"api#{name}#{len(self.calls)}",
            run_id=str(len(self.calls)),
            task_type=TaskType.API,
            state=TaskState.RUNNING,
            task_name=name,
        )
        self.statuses[status.task_id] = status
        self.started.set()
        return status

    async def wait(self, task_id, run_id, poll_interval):
        status = self.statuses[task_id]
        assert status.run_id == run_id
        if self.block:
            await self.released.wait()
        await asyncio.sleep(0)
        if not status.state.is_terminal:
            status.exit_code = 1 if status.task_name == self.fail else 0
            status.state = TaskState.FAILED if status.exit_code else TaskState.SUCCEEDED
            self.active -= 1
        return status

    async def cancel(self, task_id, run_id):
        assert self.statuses[task_id].run_id == run_id
        if self.statuses[task_id].state.is_terminal:
            return False
        self.cancelled.append(task_id)
        self.statuses[task_id].state = TaskState.CANCELLED
        self.statuses[task_id].exit_code = 130
        self.active -= 1
        self.released.set()
        return True


def batch(manager, workspace, **options):
    job = TaskBatchJob(
        stages=[
            {"task": "first", "arguments": {"days": 7}, "forward_arguments": ["days"]},
            {"task": "second", "sources": ["first"]},
            {"task": "third", "sources": ["second"]},
        ],
        lock_group="downloads",
        poll_interval=0.001,
        **options,
    )
    job.app_context = SimpleNamespace(app_config=SimpleNamespace(workspace_dir=str(workspace)))
    job.manager = manager
    return job


@pytest.mark.parametrize("continue_on_error,count", [(False, 2), (True, 3)])
def test_waits_records_lineage_and_applies_failure_policy(tmp_path, continue_on_error, count):
    async def check():
        manager = Manager(fail="second")
        result = await batch(manager, tmp_path, continue_on_error=continue_on_error).execute({"days": 9})
        assert len(manager.calls) == count
        assert manager.max_active == 1
        assert manager.calls[0][1]["days"] == 9
        assert manager.calls[1][1]["source_tasks"] == "api#first#1"
        assert not result.success
        assert result.answer["exit_code"] == 1
        assert len(result.answer["stages"]) == count

    asyncio.run(check())


def test_shared_group_waits_across_job_instances(tmp_path):
    async def check():
        manager = Manager(block=True)
        first = asyncio.create_task(batch(manager, tmp_path).execute({}))
        await manager.started.wait()
        second = asyncio.create_task(batch(manager, tmp_path).execute({}))
        await asyncio.sleep(0.02)
        assert len(manager.calls) == 1
        manager.released.set()
        results = await asyncio.gather(first, second)
        assert all(result.success for result in results)
        assert manager.max_active == 1
        assert [name for name, _ in manager.calls] == ["first", "second", "third"] * 2

    asyncio.run(check())


def test_cancel_waiter_and_running_batch_release_lock_after_worker_stops(tmp_path):
    async def check():
        manager = Manager(block=True)
        first = asyncio.create_task(batch(manager, tmp_path).execute({}))
        await manager.started.wait()
        second = asyncio.create_task(batch(manager, tmp_path).execute({}))
        await asyncio.sleep(0.02)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert manager.cancelled == ["api#first#1"]
        assert manager.active == 0
        with (tmp_path / ".locks/downloads.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    asyncio.run(check())


def test_cancellation_during_submission_retains_lock_and_handle(tmp_path):
    async def check():
        acknowledged = asyncio.Event()

        class SlowManager(Manager):
            async def submit(self, argv):
                status = await super().submit(argv)
                await acknowledged.wait()
                return status

        manager = SlowManager()
        execution = asyncio.create_task(batch(manager, tmp_path).execute({}))
        await manager.started.wait()
        execution.cancel()
        await asyncio.sleep(0.02)
        assert not execution.done()
        with (tmp_path / ".locks/downloads.lock").open("a+b") as lock:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acknowledged.set()
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert manager.active == 0
        assert manager.cancelled == ["api#first#1"]

    asyncio.run(check())


def test_wait_error_stops_worker_before_next_stage(tmp_path):
    async def check():
        class WaitErrorManager(Manager):
            async def wait(self, task_id, run_id, poll_interval):
                if not self.cancelled and len(self.calls) == 1:
                    raise RuntimeError("polling failed")
                return await super().wait(task_id, run_id, poll_interval)

        manager = WaitErrorManager()
        result = await batch(manager, tmp_path, continue_on_error=True).execute({})
        assert not result.success
        assert len(manager.calls) == 3
        assert manager.active == 0
        assert manager.max_active == 1
        assert manager.cancelled == ["api#first#1"]

    asyncio.run(check())


@pytest.mark.parametrize("stages", [[], [{"task": "a"}, {"task": "a"}], [{"task": "a", "sources": ["b"]}]])
def test_invalid_stage_plans_rejected(stages):
    with pytest.raises(ValueError):
        TaskBatchJob(stages=stages)


def test_cleanup_failure_blocks_group_until_exact_run_can_be_stopped(tmp_path):
    async def check():
        class FaultyManager(Manager):
            broken = True

            async def wait(self, task_id, run_id, poll_interval):
                if len(self.calls) == 1 and not self.cancelled:
                    raise RuntimeError("polling failed")
                return await super().wait(task_id, run_id, poll_interval)

            async def cancel(self, task_id, run_id):
                if self.broken:
                    raise RuntimeError("termination failed")
                return await super().cancel(task_id, run_id)

        manager = FaultyManager()
        first = batch(manager, tmp_path, continue_on_error=True)
        result = await first.execute({})
        stage = result.answer["stages"][0]
        assert not result.success
        assert stage["state"] == "cleanup_failed"
        assert stage["error"] == "RuntimeError: polling failed"
        assert stage["cleanup_error"] == "RuntimeError: termination failed"
        assert stage["task_id"] == "api#first#1" and stage["run_id"] == "1"
        assert len(manager.calls) == manager.active == 1
        assert (tmp_path / ".locks/downloads.blocked.json").exists()
        with pytest.raises(RuntimeError, match="blocked"):
            await batch(manager, tmp_path).execute({})
        assert len(manager.calls) == 1
        manager.broken = False
        assert (await batch(manager, tmp_path).execute({})).success
        assert manager.max_active == 1
        assert manager.active == 0
        assert not (tmp_path / ".locks/downloads.blocked.json").exists()
        with pytest.raises(ExceptionGroup, match="cleanup failed"):
            await first._close()

    asyncio.run(check())


def test_stream_close_stops_owned_worker_and_releases_group(tmp_path):
    async def check():
        manager = Manager(block=True)
        job = batch(manager, tmp_path)
        await job.start()
        execution = asyncio.create_task(job.run({}, {}))
        await manager.started.wait()
        await job.close()
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert not job.is_started
        assert manager.active == 0
        assert manager.cancelled == ["api#first#1"]
        assert not job._executions
        with (tmp_path / ".locks/downloads.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    asyncio.run(check())


def test_stream_close_reports_cleanup_failure_and_quarantines_group(tmp_path):
    async def check():
        class BrokenManager(Manager):
            async def cancel(self, task_id, run_id):
                raise RuntimeError("cannot stop worker")

        manager = BrokenManager(block=True)
        job = batch(manager, tmp_path, continue_on_error=True)
        await job.start()
        execution = asyncio.create_task(job.run({}, {}))
        await manager.started.wait()
        with pytest.raises(ExceptionGroup, match="cleanup failed") as caught:
            await job.close()
        assert "run_id=1" in str(caught.value.exceptions[0])
        response = await execution
        assert not response.success
        assert response.answer["stages"][0]["error"].startswith("CancelledError")
        assert manager.active == len(manager.calls) == 1
        with pytest.raises(RuntimeError, match="blocked"):
            await batch(manager, tmp_path).execute({})

    asyncio.run(check())


def test_wait_error_keeps_submitted_identity_in_result(tmp_path):
    async def check():
        class ManagerWithWaitError(Manager):
            async def wait(self, task_id, run_id, poll_interval):
                raise RuntimeError("wait failed")

        manager = ManagerWithWaitError()
        response = await batch(manager, tmp_path).execute({})
        stage = response.answer["stages"][0]
        assert stage["task_id"] == "api#first#1"
        assert stage["run_id"] == "1"
        assert stage["error"] == "RuntimeError: wait failed"
        assert not stage["cleanup_error"]
        assert manager.active == 0

    asyncio.run(check())


def test_cancelled_submission_failure_does_not_quarantine_without_a_worker(tmp_path):
    async def check():
        acknowledged = asyncio.Event()

        class RejectedManager(Manager):
            async def submit(self, argv):
                self.started.set()
                await acknowledged.wait()
                raise ValueError("submission rejected")

        manager = RejectedManager()
        job = batch(manager, tmp_path)
        execution = asyncio.create_task(job.execute({}))
        await manager.started.wait()
        execution.cancel()
        await asyncio.sleep(0)
        acknowledged.set()
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert not job._cleanup_errors
        assert not (tmp_path / ".locks/downloads.blocked.json").exists()

    asyncio.run(check())
