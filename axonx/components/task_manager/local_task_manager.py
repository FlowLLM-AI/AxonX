"""Run local task workers while keeping task state in memory."""

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
import importlib
import json
import os
from pathlib import Path
import signal
import socket
import sys

from .base_task_manager import BaseTaskManager
from ..component_registry import R
from ..plugin_component import PluginComponent
from ...constants import AXONX_TASK_STATUS_FD
from ...enumeration import ComponentEnum, TaskState
from ...schema import TaskStatus
from ...task import BaseTask

_LOG_LIMIT = 1024 * 1024


@dataclass
class _Execution:
    target: str
    config: dict
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    runner: asyncio.Task | None = None
    process: asyncio.subprocess.Process | None = None


@R.register("local")
class LocalTaskManager(BaseTaskManager):
    """Launch isolated workers and accept their complete status snapshots."""

    def __init__(self, max_concurrency=1, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        if not self.name or Path(self.name).name != self.name or self.name in {".", ".."}:
            raise ValueError("Manager name must be a simple directory name")
        self.max_concurrency = max_concurrency
        self._statuses: dict[str, TaskStatus] = {}
        self._executions: dict[str, _Execution] = {}
        self._pending: deque[str] = deque()
        self._running: set[str] = set()
        self._logs: dict[str, bytearray] = {}
        self._accepting = False
        self.directory: Path | None = None
        self.plugin = self.bind("default", PluginComponent)

    @property
    def state_path(self) -> Path:
        if self.directory is None:
            raise RuntimeError("Task manager is not started")
        return self.directory / "state.json"

    async def _start(self):
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")
        self.directory = self.workspace_path.resolve() / "tasks" / self.name
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.state_path.is_file():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._statuses = {
                task_id: TaskStatus.model_validate(status) for task_id, status in data.get("tasks", {}).items()
            }
        self._accepting = True

    async def _close(self):
        self._accepting = False
        await asyncio.gather(*(self.cancel(task_id) for task_id in tuple(self._executions)), return_exceptions=True)
        payload = {
            "version": 1,
            "tasks": {task_id: status.model_dump(mode="json") for task_id, status in self._statuses.items()},
        }
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(self.state_path)

    def _load_task(self, name):
        target = self.plugin.resolve_task(name) if self.plugin is not None else None
        if target is None:
            cls = self.app_context.registry.get(ComponentEnum.TASK, name)
            if not isinstance(cls, type) or not issubclass(cls, BaseTask):
                raise ValueError(f"Unknown task: {name}")
            target = f"{cls.__module__}:{cls.__qualname__}"
        else:
            module_name, qualname = target.split(":", 1)
            with R.preserve(allow_mutation=True):
                cls = importlib.import_module(module_name)
                for part in qualname.split("."):
                    cls = getattr(cls, part)
        if not isinstance(cls, type) or not issubclass(cls, BaseTask):
            raise TypeError("Task target must subclass BaseTask")
        if "<locals>" in cls.__qualname__ or cls.__module__ == "__main__":
            raise ValueError("Task must be defined in an importable module")
        return cls, target

    def _new_task_id(self, cls, config):
        task_id = config.generate_task_id(cls.task_type)
        if task_id in self._statuses or task_id in self._executions:
            raise ValueError(f"Task already exists: {task_id}")
        return task_id

    async def submit(self, task, config=None, *, suffix=None):
        if not self._accepting:
            raise RuntimeError("Task manager is not running")
        cls, target = self._load_task(task)
        raw_config = dict(config or {})
        if "task_id" in raw_config or "task_type" in raw_config:
            raise ValueError("task_id and task_type are managed internally")
        configured_suffix = raw_config.get("task_id_suffix")
        if suffix is not None and configured_suffix not in {None, suffix}:
            raise ValueError("suffix conflicts with task_id_suffix")
        if suffix is not None:
            raw_config["task_id_suffix"] = suffix
        task_config = cls.config_cls.model_validate(raw_config)
        task_id = self._new_task_id(cls, task_config)
        self._logs[task_id] = bytearray()
        execution = self._executions[task_id] = _Execution(
            target=target,
            config=task_config.model_dump(mode="json"),
        )
        self._statuses[task_id] = TaskStatus(task_id=task_id, task_type=cls.task_type)
        self._pending.append(task_id)
        self._dispatch()
        return task_id

    def _dispatch(self):
        if not self._accepting:
            return
        while self._pending and len(self._running) < self.max_concurrency:
            task_id = self._pending.popleft()
            execution = self._executions[task_id]
            if execution.stop.is_set():
                self._mark_cancelled(task_id)
                self._finish_execution(task_id)
                continue
            self._running.add(task_id)
            execution.runner = asyncio.create_task(self._run(task_id, execution), name=f"task:{task_id}")

    async def list_task_ids(self):
        return sorted(self._statuses.keys() | self._executions.keys())

    async def get_status(self, task_id):
        return self._statuses[task_id].model_copy(deep=True)

    async def wait(self, task_id, timeout=None):
        if task_id not in self._statuses and task_id not in self._executions:
            raise KeyError(task_id)
        execution = self._executions.get(task_id)
        if execution:
            await asyncio.wait_for(execution.done.wait(), timeout)
        return await self.get_status(task_id)

    async def cancel(self, task_id):
        execution = self._executions.get(task_id)
        if task_id not in self._statuses and execution is None:
            raise KeyError(task_id)
        if execution:
            execution.stop.set()
            if task_id in self._pending:
                self._pending.remove(task_id)
                self._mark_cancelled(task_id)
                self._finish_execution(task_id)
            await execution.done.wait()
        return await self.get_status(task_id)

    async def logs(self, task_id, limit=65536):
        if not isinstance(limit, int) or not 0 < limit <= _LOG_LIMIT:
            raise ValueError(f"Log limit must be between 1 and {_LOG_LIMIT} bytes")
        if task_id not in self._statuses:
            raise KeyError(task_id)
        return bytes(self._logs.get(task_id, b"")[-limit:]).decode("utf-8", errors="replace")

    async def _read_output(self, task_id, stream):
        while chunk := await stream.read(65536):
            log = self._logs[task_id]
            log.extend(chunk)
            if len(log) > _LOG_LIMIT:
                del log[:-_LOG_LIMIT]

    async def _read_status(self, task_id, stream):
        stream.setblocking(False)
        reader, writer = await asyncio.open_connection(sock=stream, limit=_LOG_LIMIT)
        try:
            while line := await reader.readline():
                incoming = TaskStatus.model_validate_json(line)
                current = self._statuses[task_id]
                if incoming.task_id != task_id or incoming.task_type != current.task_type:
                    raise ValueError(f"Invalid status identity for Task {task_id}")
                if not self._executions[task_id].stop.is_set():
                    self._statuses[task_id] = incoming
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    def _signal(process, sig):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, sig)

    async def _run(self, task_id, execution):
        readers = []
        parent_stream = child_stream = None
        try:
            if execution.stop.is_set():
                self._mark_cancelled(task_id)
                return

            environment = {**os.environ, **self.app_context.app_config.environment}
            parent_stream, child_stream = socket.socketpair()
            environment[AXONX_TASK_STATUS_FD] = str(child_stream.fileno())
            command = [sys.executable, "-m", "axonx.task.worker"]
            process = execution.process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=environment,
                pass_fds=(child_stream.fileno(),),
                start_new_session=True,
            )
            child_stream.close()
            child_stream = None
            readers = [
                asyncio.create_task(self._read_output(task_id, process.stdout)),
                asyncio.create_task(self._read_status(task_id, parent_stream)),
            ]
            parent_stream = None
            payload = json.dumps(
                {"target": execution.target, "config": execution.config}, ensure_ascii=False, allow_nan=False
            )
            process.stdin.write(payload.encode())
            await process.stdin.drain()
            process.stdin.close()
            waiter = asyncio.create_task(process.wait())
            stopped = asyncio.create_task(execution.stop.wait())
            done, _ = await asyncio.wait({waiter, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if execution.stop.is_set():
                if waiter not in done:
                    self._signal(process, signal.SIGKILL)
                    await waiter
                self._mark_cancelled(task_id)
            else:
                await waiter
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)
            await asyncio.gather(*readers)
            if not self._statuses[task_id].state.is_terminal:
                message = (
                    f"Task worker exited with code {process.returncode}"
                    if process.returncode
                    else "Task worker exited without reporting a terminal status"
                )
                self._mark_failed(task_id, message, process.returncode or 1)
        except Exception as exc:
            self.logger.error(f"Task worker {task_id} failed: {type(exc).__name__}: {exc}")
            if execution.stop.is_set():
                self._mark_cancelled(task_id)
            elif not self._statuses[task_id].state.is_terminal:
                self._mark_failed(task_id, f"{type(exc).__name__}: {exc}")
        finally:
            if child_stream is not None:
                child_stream.close()
            if parent_stream is not None:
                parent_stream.close()
            if execution.process and execution.process.returncode is None:
                self._signal(execution.process, signal.SIGKILL)
                await execution.process.wait()
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            self._running.discard(task_id)
            self._finish_execution(task_id)
            self._dispatch()

    def _finish_execution(self, task_id):
        execution = self._executions.pop(task_id, None)
        if execution is not None:
            execution.done.set()

    def _mark_cancelled(self, task_id):
        status = self._statuses[task_id]
        status.state = TaskState.CANCELLED
        status.finished_at = datetime.now(UTC)
        status.exit_code = 130

    def _mark_failed(self, task_id, error, exit_code=1):
        status = self._statuses[task_id]
        status.state = TaskState.FAILED
        status.finished_at = datetime.now(UTC)
        status.error = error
        status.exit_code = exit_code
