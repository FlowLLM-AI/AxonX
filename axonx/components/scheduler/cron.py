"""Cron-based Job scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from ...task.runtime.source import TASK_SOURCE
from ...task.schemas.lifecycle import ScheduleTrigger, TaskSource
from ..registry import provider
from .base import BaseScheduler

ConcurrencyPolicy = Literal["forbid", "allow", "replace"]


@provider("cron")
class CronScheduler(BaseScheduler):
    """Trigger one configured Job according to a cron expression."""

    def __init__(
        self,
        job: str,
        cron: str,
        arguments: Mapping[str, Any] | None = None,
        timezone: str | None = None,
        concurrency_policy: ConcurrencyPolicy = "forbid",
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if not isinstance(job, str) or not job:
            raise ValueError("Cron scheduler job must be a non-empty name")
        if not isinstance(cron, str) or not croniter.is_valid(cron):
            raise ValueError(f"Invalid cron expression: {cron!r}")
        if concurrency_policy not in {"forbid", "allow", "replace"}:
            raise ValueError(f"Invalid concurrency policy: {concurrency_policy!r}")

        timezone_name = timezone or self.app_config.timezone
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone_name!r}") from None

        self.job_name = job
        self.description = description
        self.cron = cron
        self.arguments = dict(arguments or {})
        self.concurrency_policy = concurrency_policy
        self.last_trigger: dict | None = None
        self._runner: asyncio.Task[None] | None = None
        self._executions: set[asyncio.Task[None]] = set()

    async def _start(self) -> None:
        job = self.app_context.jobs.get(self.job_name)
        if job is None:
            raise ValueError(f"Unknown scheduled Job: {self.job_name!r}")
        job.validate_arguments(self.arguments)
        self._runner = asyncio.create_task(
            self._run_forever(),
            name=f"axonx-scheduler:{self.name}",
        )

    def describe(self) -> dict:
        return {
            "name": self.name,
            "job": self.job_name,
            "description": self.description or self.app_context.jobs[self.job_name].description,
            "cron": self.cron,
            "timezone": str(self.timezone),
            "arguments": deepcopy(self.arguments),
            "concurrency_policy": self.concurrency_policy,
            "next_run_at": self._next_run().isoformat() if self.is_started else None,
            "running": sum(not task.done() for task in self._executions),
            "last_trigger": deepcopy(self.last_trigger),
        }

    def _next_run(self, now: datetime | None = None) -> datetime:
        return croniter(self.cron, now or datetime.now(self.timezone)).get_next(datetime)

    def _next_delay(self) -> float:
        now = datetime.now(self.timezone)
        return max(0.0, self._next_run(now).timestamp() - now.timestamp())

    async def _run_forever(self) -> None:
        while True:
            try:
                delay = self._next_delay()
            except Exception:
                self.logger.exception("Cron schedule calculation failed")
                await asyncio.sleep(1)
                continue
            await asyncio.sleep(delay)
            await self._trigger()

    async def _trigger(self) -> None:
        active = {task for task in self._executions if not task.done()}
        if active and self.concurrency_policy == "forbid":
            self.logger.warning(f"Skipping overlapping run of Job {self.job_name!r}")
            return
        if active and self.concurrency_policy == "replace":
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)

        task = asyncio.create_task(
            self._execute(),
            name=f"axonx-schedule:{self.name}:{self.job_name}",
        )
        self._executions.add(task)
        task.add_done_callback(self._executions.discard)

    async def _execute(self) -> None:
        trigger = ScheduleTrigger(
            name=self.name, job=self.job_name, trigger_id=uuid4().hex, triggered_at=datetime.now(UTC)
        )
        result = {**trigger.model_dump(mode="json"), "state": "running", "error": ""}
        self.last_trigger = result
        token = TASK_SOURCE.set(TaskSource(kind="submit", schedule=trigger))
        try:
            response = await self.app_context.dispatcher.run(self.job_name, self.arguments)
        except asyncio.CancelledError:
            result["state"] = "cancelled"
            raise
        except Exception as exc:
            result.update(state="failed", error=str(exc))
            self.logger.exception(f"Scheduled Job {self.job_name!r} raised")
        else:
            result.update(
                state="succeeded" if response.success else "failed",
                error="" if response.success else str(response.answer),
            )
            if not response.success:
                self.logger.warning(f"Scheduled Job {self.job_name!r} failed: {response.answer}")
        finally:
            TASK_SOURCE.reset(token)

    async def _close(self) -> None:
        runner, self._runner = self._runner, None
        if runner is not None:
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner
        tasks = tuple(self._executions)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._executions.clear()
