"""Declarative Task batches with shared locking and explicit failure policy."""

from __future__ import annotations

import asyncio
import fcntl
import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..registry import provider
from .contracts import JobResponse
from .managed import ManagedTaskJob, TaskStageError
from ...utils.fs import atomic_write_json


class TaskStage(BaseModel):
    """One Task's fixed arguments, caller overrides and upstream stage names."""

    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    forward_arguments: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class TaskStageResult(BaseModel):
    """Uniform stage outcome, including identity when submission succeeded."""

    task: str
    task_id: str | None = None
    run_id: str | None = None
    state: str = "failed"
    exit_code: int = 1
    error: str = ""
    cleanup_error: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


@provider("task_batch")
class TaskBatchJob(ManagedTaskJob):
    """Wait for every Task before advancing; optionally serialize related Jobs."""

    def __init__(
        self,
        stages: Sequence[TaskStage | Mapping[str, Any]],
        lock_group: str | None = None,
        continue_on_error: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.stages = tuple(TaskStage.model_validate(stage) for stage in stages)
        if not self.stages:
            raise ValueError("Task batch requires at least one stage")
        seen = set()
        for stage in self.stages:
            if stage.task in seen:
                raise ValueError(f"Duplicate batch stage: {stage.task}")
            if missing := set(stage.sources) - seen:
                raise ValueError(f"Stage {stage.task} references unavailable sources: {sorted(missing)}")
            seen.add(stage.task)
        if lock_group is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", lock_group):
            raise ValueError("lock_group must contain only letters, digits, hyphens or underscores")
        self.lock_group = lock_group
        self.continue_on_error = continue_on_error

    @asynccontextmanager
    async def _batch_lock(self) -> AsyncIterator[Path | None]:
        if self.lock_group is None:
            yield None
            return
        path = self.workspace_path / ".locks" / f"{self.lock_group}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(self.poll_interval)
            blocked = path.with_suffix(".blocked.json")
            try:
                if blocked.exists():
                    unresolved = json.loads(blocked.read_text())
                    try:
                        await self.manager.cancel(unresolved["task_id"], unresolved["run_id"])
                    except Exception as exc:
                        raise RuntimeError(f"Batch group {self.lock_group} is blocked: {unresolved}") from exc
                    blocked.unlink()
                yield blocked
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    async def execute(self, arguments: Mapping[str, Any]) -> JobResponse:
        async with self._batch_lock() as blocked:
            results: list[TaskStageResult] = []
            sources: dict[str, str] = {}
            for stage in self.stages:
                config = {
                    **stage.arguments,
                    **{key: arguments[key] for key in stage.forward_arguments if key in arguments},
                }
                upstream = [sources[name] for name in stage.sources if name in sources]
                if upstream:
                    config["source_tasks"] = ",".join(upstream)
                try:
                    status = await self.run_stage(stage.task, config)
                    result = TaskStageResult(
                        task=stage.task,
                        task_id=status.task_id,
                        run_id=status.run_id,
                        state=status.state.value,
                        exit_code=status.exit_code,
                        error=status.error,
                        result=status.result,
                    )
                except TaskStageError as exc:
                    result = TaskStageResult(
                        task=stage.task,
                        task_id=exc.handle.task_id if exc.handle else None,
                        run_id=exc.handle.run_id if exc.handle else None,
                        state="cleanup_failed" if exc.cleanup_error else "failed",
                        error=f"{type(exc.cause).__name__}: {exc.cause}",
                        cleanup_error=(
                            f"{type(exc.cleanup_error).__name__}: {exc.cleanup_error}" if exc.cleanup_error else ""
                        ),
                    )
                results.append(result)
                if result.task_id:
                    sources[stage.task] = result.task_id
                if result.cleanup_error:
                    if blocked is not None:
                        atomic_write_json(blocked, result.model_dump())
                    break
                if result.exit_code and not self.continue_on_error:
                    break
            exit_code = next((result.exit_code for result in results if result.exit_code), 0)
            return JobResponse(
                answer={"exit_code": exit_code, "stages": [result.model_dump() for result in results]},
                success=exit_code == 0,
            )
