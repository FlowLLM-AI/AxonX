"""Launch local task workers and store externally reported status."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import signal
import sys

from .base_task_manager import BaseTaskManager
from ..component_registry import R
from ...constants import AXONX_SERVICE_INFO
from ...enumeration import TaskState
from ...schema import TaskStatus


@R.register("local")
class LocalTaskManager(BaseTaskManager):
    """Launch workers without deriving or monitoring their task status."""

    def __init__(self, version: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.version = version
        self._statuses: dict[str, TaskStatus] = {}

    @property
    def task_manager_dir(self) -> Path:
        directory = self.workspace_path.resolve() / "task_manager"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def status_path(self) -> Path:
        return self.task_manager_dir / "status.json"

    def _save_status(self):
        payload = {
            "version": self.version,
            "tasks": [status.model_dump(mode="json") for status in self._statuses.values()],
        }
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(self.status_path)

    async def _start(self):
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")
        if self.status_path.is_file():
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
            if data.get("version") == self.version:
                statuses = (TaskStatus.model_validate(status) for status in data.get("tasks", []))
                self._statuses = {status.task_id: status for status in statuses}

    async def submit(self, argv: Sequence[str]) -> None:
        if not self.is_started:
            raise RuntimeError("Task manager is not running")
        if isinstance(argv, (str, bytes)) or not all(isinstance(value, str) for value in argv):
            raise TypeError("Task arguments must be a sequence of strings")
        environment = dict(self.app_config.environment)
        if service_info := os.environ.get(AXONX_SERVICE_INFO):
            environment[AXONX_SERVICE_INFO] = service_info
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "axonx.cli",
            "exec",
            *argv,
            env=environment,
            start_new_session=True,
        )

    async def set_status(self, task_id: str, status: TaskStatus) -> None:
        if task_id != status.task_id:
            raise ValueError("Task status ID does not match task_id")
        self._statuses[task_id] = status.model_copy(deep=True)
        self._save_status()

    async def list_task_ids(self):
        return sorted(self._statuses)

    async def get_status(self, task_id):
        return self._statuses[task_id].model_copy(deep=True)

    async def cancel(self, task_id: str) -> bool:
        status = self._statuses[task_id]
        if status.pid is None or status.state.is_terminal or not self._signal(status.pid, signal.SIGKILL):
            return False
        status.state = TaskState.CANCELLED
        status.finished_at = datetime.now(UTC)
        status.exit_code = 130
        self._save_status()
        return True

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> bool:
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return False
        return True
