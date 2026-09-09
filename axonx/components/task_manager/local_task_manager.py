"""One fresh process per submission, with bounded concurrency and durable records."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import signal
import sys
import time
from uuid import uuid4

from .base_task_manager import BaseTaskManager
from ..component_registry import R
from ...enumeration import (
    ComponentEnum,
    TaskState,
)
from ...schema import TaskRun, TaskStep
from ...task import BaseTask
from ..plugin_component import PluginComponent


@dataclass
class _Execution:
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    force: asyncio.Event = field(default_factory=asyncio.Event)
    future: asyncio.Task | None = None
    process: asyncio.subprocess.Process | None = None


@R.register("local")
class LocalTaskManager(BaseTaskManager):
    """Run synchronous tasks in isolated local process groups."""

    def __init__(
        self,
        max_concurrency=1,
        cancel_timeout=5.0,
        terminate_timeout=2.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        if cancel_timeout < 0 or terminate_timeout <= 0:
            raise ValueError("Invalid cancellation timeouts")
        if not self.name or Path(self.name).name != self.name or self.name in {".", ".."}:
            raise ValueError("Manager name must be a simple directory name")
        self.cancel_timeout = cancel_timeout
        self.terminate_timeout = terminate_timeout
        self._slots = asyncio.Semaphore(max_concurrency)
        self._runs = {}
        self._executions = {}
        self._accepting = False
        self.directory: Path | None = None
        self.plugin = self.bind("default", PluginComponent)

    async def _start(self):
        if os.name != "posix":
            raise NotImplementedError(
                "LocalTaskManager currently supports macOS and Linux process groups",
            )
        self.directory = self.workspace_path.expanduser().resolve() / "tasks" / self.name
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.glob("*/run.json"):
            record = TaskRun.model_validate_json(path.read_text())
            if record.id != path.parent.name:
                raise ValueError(f"Invalid task record: {path}")
            if not record.state.is_terminal:
                record.state = TaskState.LOST
                record.error = "Application stopped without completing this run; not automatically resumed"
                record.finished_at = time.time()
            self._runs[record.id] = record
            self._save(record)
        self._accepting = True

    async def _close(self):
        self._accepting = False
        await asyncio.gather(*(self.cancel(key) for key in tuple(self._executions)))
        self._executions.clear()

    def _path(self, run_id):
        # Only known IDs reach filesystem access.
        if run_id not in self._runs:
            raise KeyError(run_id)
        if self.directory is None:
            raise RuntimeError("Task manager is not started")
        return self.directory / run_id

    def _save(self, record):
        path = self._path(record.id) / "run.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(record.model_dump_json(indent=2))
        temporary.replace(path)

    async def submit(self, task, config=None):
        if not self._accepting:
            raise RuntimeError("Task manager is not running")
        task_config = config or {}
        target = self.plugin.resolve_task(task) if self.plugin is not None else None
        if target is None:
            cls = self.app_context.registry.get(ComponentEnum.TASK, task)
            if cls is None or not issubclass(cls, BaseTask):
                raise ValueError(f"Unknown task: {task}")
            if "<locals>" in cls.__qualname__ or cls.__module__ == "__main__":
                raise ValueError("Task must be defined in an importable module")
            target = f"{cls.__module__}:{cls.__qualname__}"
            task_config = cls.config_class.model_validate(task_config).model_dump(
                mode="json",
            )
        run_id = uuid4().hex
        payload = {
            "target": target,
            "config": task_config,
            "manager": self.name,
            "run_id": run_id,
        }
        serialized = json.dumps(payload, allow_nan=False)
        directory = self.directory / run_id
        directory.mkdir()
        (directory / "request.json").write_text(serialized)
        record = TaskRun(id=run_id, task=task, created_at=time.time())
        self._runs[run_id] = record
        self._save(record)
        execution = _Execution()
        self._executions[run_id] = execution
        execution.future = asyncio.create_task(
            self._run(record, execution),
            name=f"task:{run_id}",
        )
        return run_id

    def _progress(self, record):
        path = self._path(record.id) / "progress.json"
        if path.exists():
            data = json.loads(path.read_text())
            for index, step in enumerate(data["task_steps"]):
                self._update_task_step(record, index, step)

    @staticmethod
    def _update_task_step(record, step_index, task_step):
        if not isinstance(step_index, int) or isinstance(step_index, bool) or step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        step = TaskStep.model_validate(task_step)
        if step_index > len(record.task_steps):
            raise ValueError("step_index cannot skip task steps")
        if step_index == len(record.task_steps):
            record.task_steps.append(step)
            return

        current = record.task_steps[step_index]
        if current.name != step.name:
            raise ValueError("A task step name cannot change")
        if current.percentage is not None and step.percentage is None:
            return
        if current.percentage is not None and step.percentage is not None and step.percentage < current.percentage:
            return
        record.task_steps[step_index] = step

    async def report_progress(self, run_id, step_index, task_step):
        record = self._runs[run_id]
        if run_id not in self._executions:
            raise ValueError("Cannot update progress for a finished task")
        self._update_task_step(record, step_index, task_step)
        self._save(record)
        return record.model_copy(deep=True)

    async def status(self, run_id=None):
        if run_id is None:
            return [await self.status(key) for key in self._runs]
        record = self._runs[run_id]
        self._progress(record)
        return record.model_copy(deep=True)

    async def wait(self, run_id, timeout=None):
        if run_id not in self._runs:
            raise KeyError(run_id)
        execution = self._executions.get(run_id)
        if execution:
            await asyncio.wait_for(asyncio.shield(execution.future), timeout)
        return await self.status(run_id)

    async def cancel(self, run_id):
        return await self._stop(run_id, force=False)

    async def kill(self, run_id):
        return await self._stop(run_id, force=True)

    async def _stop(self, run_id, force):
        record = self._runs[run_id]
        if not record.state.is_terminal:
            execution = self._executions[run_id]
            record.state = TaskState.CANCELLING
            (self._path(run_id) / "cancel").touch()
            if force:
                execution.force.set()
            execution.stop.set()
            self._save(record)
            await asyncio.shield(execution.future)
        return await self.status(run_id)

    async def logs(self, run_id, limit=65536):
        if not isinstance(limit, int) or not 0 < limit <= 1048576:
            raise ValueError("Log limit must be between 1 and 1048576 bytes")
        path = self._path(run_id) / "output.log"
        if not path.exists():
            return ""
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - limit))
            return stream.read(limit).decode("utf-8", errors="replace")

    @staticmethod
    def _signal(process, sig):
        with suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(process.pid, sig)
            elif process.returncode is None:
                if sig == signal.SIGKILL:
                    process.kill()
                else:
                    process.terminate()

    async def _finish_process(self, execution, waiter):
        process = execution.process
        # Cooperate between task-local steps, but a blocking native call has a bounded grace period.
        deadline = asyncio.get_running_loop().time() + self.cancel_timeout
        while not waiter.done() and not execution.force.is_set() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)
        if not waiter.done():
            self._signal(
                process,
                signal.SIGKILL if execution.force.is_set() else signal.SIGTERM,
            )
            deadline = asyncio.get_running_loop().time() + self.terminate_timeout
            while not waiter.done() and not execution.force.is_set() and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.05)
        # Also reap descendants left by an already-exited parent.
        self._signal(process, signal.SIGKILL)
        await waiter

    async def _run(self, record, execution):
        acquired = False
        waiter = stopper = None
        try:
            slot = asyncio.create_task(self._slots.acquire())
            queued_stop = asyncio.create_task(execution.stop.wait())
            try:
                await asyncio.wait(
                    {slot, queued_stop},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not slot.done():
                    slot.cancel()
                queued_stop.cancel()
                await asyncio.gather(slot, queued_stop, return_exceptions=True)
                acquired = not slot.cancelled() and slot.exception() is None
            if not execution.stop.is_set():
                directory = self._path(record.id)
                environment = {**os.environ, **self.app_context.app_config.environment}
                with (directory / "output.log").open("wb") as output:
                    execution.process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "axonx.components.task_manager.worker",
                        str(directory / "request.json"),
                        stdout=output,
                        stderr=output,
                        env=environment,
                        start_new_session=os.name == "posix",
                    )
                record.pid = execution.process.pid
                record.started_at = time.time()
                if not execution.stop.is_set():
                    record.state = TaskState.RUNNING
                self._save(record)
                waiter = asyncio.create_task(execution.process.wait())
                stopper = asyncio.create_task(execution.stop.wait())
                await asyncio.wait(
                    {waiter, stopper},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if execution.stop.is_set():
                    await self._finish_process(execution, waiter)
                else:
                    await waiter
                    self._signal(execution.process, signal.SIGKILL)
                record.exit_code = execution.process.returncode
                self._progress(record)
                if not execution.stop.is_set():
                    result_path = directory / "result.json"
                    result = json.loads(result_path.read_text()) if result_path.exists() else {}
                    if record.exit_code != 0 or "error" in result or "output" not in result:
                        raise RuntimeError(
                            result.get(
                                "error",
                                f"Worker exited with code {record.exit_code}; see logs",
                            ),
                        )
                    if not isinstance(result["output"], dict):
                        raise TypeError("Task output must be a JSON object")
                    record.result = result["output"]
                    record.state = TaskState.SUCCEEDED
        except Exception as exc:
            record.error = str(exc)
            record.state = TaskState.FAILED
        finally:
            if execution.process and execution.process.returncode is None:
                self._signal(execution.process, signal.SIGKILL)
                await execution.process.wait()
            if stopper:
                stopper.cancel()
                with suppress(asyncio.CancelledError):
                    await stopper
            if execution.stop.is_set():
                record.state = TaskState.CANCELLED
            record.finished_at = time.time()
            self._save(record)
            if acquired:
                self._slots.release()
            self._executions.pop(record.id, None)
